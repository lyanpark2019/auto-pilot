---
name: vault-score
description: >
  Run structural + content scoring on existing vault. No PM loop. Use after manual
  edits to re-check quality. Also dispatches adversarial audit (--audit), factual
  content verification (--content-verify), and vault-internal drift detection (--drift).
  Absorbs: /vault-audit, /vault-content-verify, /vault-drift.
argument-hint: "[<vault_path>] [--audit] [--content-verify] [--drift <repo> [--format json|md] [--out PATH]]"
allowed-tools: [Bash, Read, Task]
---

# /vault-score

Run structural + content scoring on existing vault. No PM loop. Use after manual edits to re-check quality.

## Usage

```
/vault-score [<vault-path>]                         # structural + content scores (default)
/vault-score --audit [<vault-path>]                 # adversarial strict re-score → meta/audit-rN.md
/vault-score --content-verify [<vault-path>]        # factual audit → meta/content-audit-rN.md
/vault-score --drift <repo> [--vault <path>] [--format json|md] [--out PATH]
                                                    # vault-internal drift report (read-only)

/vault-score                                        # uses last vault from ${CLAUDE_PLUGIN_DATA}/last-vault
```

> **Routing — repo code↔doc drift is NOT handled here**: a project's own `docs/` tree vs its
> source code belongs to the `doc-management` skill (AUDIT mode). `--drift` covers **vault-internal
> drift only**: an exported Obsidian/NotebookLM vault cross-checked against its source repo via
> `--doc-root <vault>`. See vault-drift routing note below.

---

## Default mode (structural + content score)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/vault/scripts/score_structural.py" "$VAULT"
python3 "${CLAUDE_PLUGIN_ROOT}/vault/scripts/score_content.py" "$VAULT"
python3 "${CLAUDE_PLUGIN_ROOT}/vault/scripts/pm_loop.py" "$VAULT"  # shows gaps + watchdog
```

Print both scores + top gaps. No worker dispatch.

---

## `--audit` mode (adversarial strict re-score)

Dispatch a general-purpose agent to perform an independent strict re-score of the vault.

Use the Task tool to launch an agent with this prompt:

> You are an adversarial auditor for a vault at `<vault>`. Re-score against the 10-dim structural rubric
> independently — do NOT trust any existing score-state.json; recompute from scratch.
>
> **Stricter calibration (auditor offsets)**:
> - confidence_balance INFERRED ≥ 78%: deduct 1pt (borderline penalty)
> - confidence_balance AMBIGUOUS ≥ 13%: deduct 1pt
> - concept_entity_depth: require ≥3 concepts AND each ≥40 words substantive (not just count)
> - wiki_articles: require ≥2 distinct inbound links AND non-empty body (not just ≥1 inbound)
> - adr_pages: verify each ADR has all 3 sections (Context/Decision/Consequences) non-empty
> - backlinks: require inbound from ≥2 DIFFERENT page types
> - graph_density: flag if density inflated by self-loops or duplicate edges
>
> **Seed independence**: use `random.SystemRandom()` or `os.urandom()` — NOT `random.Random(42)`.
> This ensures your sample differs from the internal scorer's deterministic sample.
>
> **Rubric**: read `${CLAUDE_PLUGIN_ROOT}/vault/templates/rubric.yaml` (fallback to hardcoded thresholds
> if yaml unavailable).
>
> **Spot-check sampling per dimension**: 3 random edges per category, 3 random wiki articles per category,
> 10 random source page backlinks vault-wide, 5 random `real`-tagged cross-vault links.
>
> Write `<vault>/meta/audit-r<N>.md` with:
> - Per-dim score + explicit pass/fail + 5 random spot-check examples per dim
> - "Improvements vs prev audit"
> - "Honest remaining gaps" (critical ≥3pt deduction vs minor <3pt)
> - Final verdict: PASS (≥95) or NEEDS WORK with specific worker tickets
>
> Anti-patterns: do NOT trust score-state.json; do NOT use seed=42; do NOT accept borderline scores
> without applying the stricter offsets; do NOT skip the merged top-level graph.json.
>
> After writing the audit report, print summary verdict + comparison to internal score.

After the agent returns, print summary verdict + comparison to internal score.

Default-vault fallback: `${CLAUDE_PLUGIN_DATA}/last-vault`.

---

## `--content-verify` mode (factual audit)

Dispatch a general-purpose agent to perform a sample-based factual audit of the vault.

Use the Task tool to launch an agent with this prompt:

> You are a content fact-checker for a vault at `<vault>`. Sample worker-generated content and
> cross-check against raw NotebookLM source fulltexts. Flag factual issues.
>
> **What to flag**:
> - Edges between nodes whose labels don't co-occur in any source
> - Concept summaries with claims not in source
> - ADR sections (Context/Decision/Consequences) without source grounding
> - Community labels that don't match member node themes
> - Cross-vault `real`-tagged links pointing to unrelated topics
> - Worker pages without source citations
>
> **Workflow**:
> 1. Read `<vault>/meta/score-content-state.json` as baseline.
> 2. Sample edges: 30 random INFERRED + AMBIGUOUS. For each, check whether source_label and
>    target_label token-sets co-occur in the same raw file (STRONG: same paragraph; WEAK: same file
>    different sections; NO: no co-occurrence → flag for removal/AMBIGUOUS-demotion).
> 3. Sample concept pages: 14 random. For each, parse `sources:` frontmatter, check each Summary
>    claim against cited sources.
> 4. Sample ADRs: all (~10). Check Context/Decision/Consequences against cited source notebooks.
>    Be strict — ADRs must not invent details.
> 5. Community label fit: for each community in `.graphify_labels.json`, check label tokens overlap
>    member node label themes.
> 6. Cross-vault `real` targets: 10 sample. Check sibling vault file exists AND shares topic.
> 7. Hot cache citations: parse "Top God Nodes" sections, cross-check against `.graphify_analysis.json`.
>
> **Result categories for edges**: STRONG (both tokens in same paragraph), WEAK (same file, different
> sections), NO (no co-occurrence → remove or AMBIGUOUS-demote).
>
> **Stop criteria** (report these %s even if not met):
> - ≥95% sampled edges grounded (STRONG or WEAK)
> - ≥90% concept pages grounded
> - ≥90% ADRs grounded
> - ≥95% labels fit
> - 100% cross-vault `real` targets exist
>
> Write `<vault>/meta/content-audit-r<N>.md` with summary, NO-support edge list (action: remove or
> AMBIGUOUS-demote), concept hallucinations, ADR fidelity gaps, and tickets to issue to PM.
>
> Anti-patterns: do NOT accept structural completeness as content correctness; sample only
> INFERRED/AMBIGUOUS edges (EXTRACTED are already grounded); quote raw source text in audit report.
>
> Print: edge_fact %, concept accuracy %, ADR fidelity %, hallucination flagged.

Default-vault fallback: `${CLAUDE_PLUGIN_DATA}/last-vault`.

---

## `--drift` mode (vault-internal drift, read-only)

> **Routing**: repo code↔doc drift (a project's own `docs/` tree vs its source) belongs to
> `doc-management` AUDIT mode. `--drift` covers **vault-internal drift only**: an exported
> Obsidian/NotebookLM vault cross-checked against its source repo (`--doc-root <vault>`).
> Repo-docs path is DEPRECATED here.

```bash
/vault-score --drift <repo-path>                        # default: scan repo + repo/docs/
/vault-score --drift <repo-path> --vault <path>         # docs live in separate vault
/vault-score --drift <repo-path> --format json          # machine-readable
/vault-score --drift <repo-path> --out drift.md         # write to file
```

### What it detects

| Type | Description |
|---|---|
| **Gap** | code module with public surface but no doc reference |
| **Orphan** | doc references file that no longer exists on disk |
| **Symbol drift** | doc backtick-mentions a symbol absent from claimed source files |
| **Claim drift** | doc-rendered signature differs from current code |

Manual-edit pages (`frontmatter.manual_edit: true` or `<!-- manual -->` marker) excluded.

### Implementation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/vault/pipeline/drift.py" "$REPO" [--doc-root "$VAULT"] [--format json|md] [--out PATH]
```

Pass `--doc-root <vault>` when scanning a separate vault directory. This is the read-only diagnosis path — fixing vault-internal drift means re-exporting with `/vault-build` (upsert semantics). Fixing **repo-docs** drift goes to the `doc-management` skill.

### Validated

ga4-collector (103 modules, 23 docs):
- 8 gap (retention.py, anomaly/_extraction.py, adsense/services/*)
- 24 orphan (docs/ARCHITECTURE.md → renamed files)
- 0 symbol drift (tight filter)
- 11 claim drift (e.g. `register(cli)` doc vs `register(cli_group: click.Group)` code)

### Limitations

- Python-only AST scan (TS/JS via tree-sitter TBD)
- Symbol drift requires docs to declare `source_files:` frontmatter
- Claim drift heuristic: backtick `name(args)` patterns only
