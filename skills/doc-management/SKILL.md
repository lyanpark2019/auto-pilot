---
name: doc-management
description: >-
  THE docs subsystem — one skill, three modes (REBUILD / MAINTAIN / AUDIT) that keeps a
  repo's documentation matching its code, graphify-native. This skill should be used
  whenever docs and code disagree, in any phrasing: "doc rot", "문서 개판", "docs don't
  match code", "문서 전면 재작성", "rebuild docs from code", "graphify-native docs",
  patchwork doc tree after a big refactor/migration (→ REBUILD); "doc sync", "문서
  동기화", "docs behind code", "incremental doc update", "코드 바뀐 만큼만 문서 갱신",
  stale design docs after merging a feature (→ MAINTAIN); "doc drift", "문서 최신화",
  "docs audit", "주석이 옛날 정책", "sync docs to the codebase", docs that may be
  aspirational or agent-written and need verification (→ AUDIT). Requests for a "claim
  ledger" also land here — that pattern is retired; SHA freshness + AUDIT replace it.
  NOT for: Obsidian/NotebookLM vault export (vault-build), harness bootstrap
  (setup-harness), whole-codebase quality scoring (adversarial-review-loop),
  DB-schema / env-config drift.
---

# doc-management — one doc system, three modes

The failure mode this skill kills: hand-maintained structure docs (per-module wikis,
"what-calls-what" pages) ALWAYS drift, because nothing forces them to match code.
Evidence: a 345-page hand-maintained wiki drifted from day one and was scrapped wholesale
(PickL-API 2026-06). The fix is a 3-layer split — structure is queried from the code
graph (machine-regenerated, structurally cannot drift), Why is hand-written but
historical (doesn't rot), and the repo's generated mirror goes live only through review
gates.

Canonical system spec: `references/doc-management-system.md` — the 3-layer model,
frontmatter contract, automation table (L1/L2/L3), and known limits. Read it before
changing how any mode works. This SKILL.md is the executable entry.

## Mode routing — pick first

| Symptom | Mode |
|---|---|
| Tree rotten/patchwork; structure hand-typed; per-module wikis drifting; stale policies described as current | **REBUILD** — demolish + reauthor from the graph |
| Tree healthy; code changed since docs were written; freshness script reports STALE | **MAINTAIN** — targeted per-doc refresh |
| Prose may lie about logic; docs possibly aspirational/agent-written; post-refactor truth check | **AUDIT** — read-only evidence fan-out |
| Export docs/graph to an Obsidian / NotebookLM vault | NOT here → `vault-build` |

AUDIT finds, MAINTAIN fixes, REBUILD replaces. Steady-state lifecycle: REBUILD once →
post-commit hook keeps the graph fresh → `check_design_doc_freshness.py` WARNs on stale
docs → MAINTAIN batches the refreshes → periodic AUDIT catches what machines can't.
"The user thinks it's rotten" is a hypothesis, not a finding — REBUILD's Phase 0
diagnosis decides between full rebuild and targeted cleanup; when in doubt start there.

## Gotchas (hard-won — read BEFORE running any mode)

Every row is a real incident, not a hypothetical.

| Gotcha | Mitigation |
|--------|------------|
| graphify full corpus ingests `.md` → stale docs bleed INTO the graph | always filter to code-only for the structure SoT (REBUILD Phase 1 snippet) |
| `file_type=="code"` alone insufficient — json/sh/test nodes carry it too | also filter by language extension + exclude tests/scratch paths |
| graph.json edge key is `links` (networkx), not `edges` | filter snippet handles both |
| `graphify .` first-build needs an LLM key; `cluster-only` needs `<dir>/graphify-out/graph.json` layout | use `graphify update` (AST-only, key-free) + write the canonical layout |
| Hard-coding the filtered graph under `/tmp` | repo-rooted `.graphify/code-only/` — survives reboots, MAINTAIN diffs against it later; gitignore it |
| Vault-relative cites (`intent/...`) and `[[wikilinks]]` dangle when ported into the repo | repoint to repo-relative paths; convert to standard `[text](path)` links |
| Line-number cites rot the moment a file is restructured | symbol anchors (`` `file.py` → `SYMBOL` ``) for churn-prone files; section names for `.md`→`.md` |
| Why ≠ structure — decisions/incidents are NOT in the call graph | harvest Why into `intent/` BEFORE deleting old docs ("none lost" invariant) |
| Moving a machine-read doc breaks the gate that parses it | discover `<MACHINE_READ_DOCS>` first; those files never move (live exception) |
| Archiving an ops-essential doc leaves an ops gap window | verify-restore at the original path in the SAME commit |
| Docs-only merge on a no-path-filter CI silently redeploys prod | check deploy governance; bundle docs into a code PR |
| Author cannot self-detect own P0s | dual adversarial review is mandatory, not self-servable |
| Global find-replace on a retired term rewrites correct history | read code per occurrence — some mentions are correct-historical |
| Grep alone cannot tell stale from historical | the auditor must READ the code at each occurrence |
| A claim looks verified because another doc asserts it | verify against code > tests > CLI > config — never against docs |
| Full-auto LLM rewrite + auto-commit | FORBIDDEN in every mode — unreviewed prose is how rot reproduces |
| Hand-maintained verification JSON (claim ledger) rots like any hand-maintained doc | retired pattern — SHA freshness (L3) + AUDIT replace it |

## The 3-layer model (shared by all modes)

| Layer | Source of truth | Drift defense |
|-------|-----------------|---------------|
| **What** — modules, calls, deps | code graph (graphify Tree-sitter AST, **code-only filter**); consume via `graphify query/explain` | regenerated from code; post-commit hook |
| **Why** — decisions, incidents, gotchas, governance | `intent/` layer (ADR/gotcha/history/governance), faithful-extraction-only, every entry cites a source, unknown = `(why not documented)` | inherently historical — doesn't rot |
| **Generated mirror** — repo `.claude/design/`, rules, nav, docs | generated from the two layers above with `file:line`/symbol-anchor cites; live only after dual review | L2 guard (mechanical) + L3 SHA freshness (auto-detect) + AUDIT (semantic) |

Forbidden patterns: per-module structure pages (the rot machine) · hand-mirroring
structure facts (query the graph instead) · governance restated in N pages (single SoT
page + one-line cites) · unreviewed LLM prose going live.

## MODE: REBUILD — full demolish + reauthor

Full procedure (the proven 7-phase, end-to-end-verified on PickL-API):
**`references/rebuild-phases.md`** — read it before executing. Phase map:

0. **Diagnose (hard gate)** — parallel read-only audits → explicit `disciplined` /
   `patchwork` verdict. Only `patchwork` unlocks Phases 1–7; `disciplined` exits to
   targeted cleanup (often: delete scratch, collapse a duplicated fact, distill plans
   → ADR, fix dead refs — then STOP).
1. **Code-only product graph** — `graphify update .` (AST-only) → filter graph.json
   (file_type AND extension AND path excludes) → repo-rooted
   `.graphify/code-only/graphify-out/graph.json` → `cluster-only` → validate with a
   domain query (fixtures returned = filter failed).
2. **Vault workbench** — `_graph/` artifacts + `intent/` Why-harvest (cite sources,
   never invent, harvest BEFORE deleting anything).
3. **Author FROM the graph** — one agent per subsystem (~8-10 topic docs, NOT
   per-module): query → READ the actual source surfaced → write with cites + Why.
4. **Rewrite the repo trees, clean-slate** — only rewritten+reviewed docs go live;
   everything else → `_archive/` (frozen, guard-exempt, future verified-extraction
   source). Root docs (README / CLAUDE.md / AGENTS.md / OVERVIEW / docs-index) get a
   fresh rewrite against the new structure. Live exceptions: GENERATED artifacts +
   `<MACHINE_READ_DOCS>` (gate-parsed docs never move). Ops-essential docs:
   verify-restore at the original path in the SAME commit. Dangling-ref sweep.
5. **Dual adversarial review** — Codex-adversarial + cold Claude in parallel; open
   every cited file, refute every claim; fix ALL P0/P1; repeat until BOTH APPROVE
   with zero new findings. Not optional, not self-servable.
6. **Anti-re-rot lock** — L2 guard (`check-doc-reference-integrity.mjs`) wired into
   the local gate with `DOC_ROOTS` repointed + `RETIRED_SYMBOLS` fed with the names
   just deleted; `graphify hook install`; L3 freshness script installed
   (`check_design_doc_freshness.py`); document the guard's blind spots.
7. **Ship tail** — local gate EXIT 0 → docs branch → deploy-boundary check (no
   autonomous docs-only merge) → demote the vault to a re-exported mirror → handoff
   memory.

## MODE: MAINTAIN — freshness scan → targeted refresh

The steady-state mode. Detection is automatic, refresh is reviewed.

**Inputs.** The graph-freshness watcher (`${CLAUDE_PLUGIN_ROOT}/hooks/doc-sync-update.sh`,
PostToolUse) marks `graphify-out/needs_update` whenever code is edited in a
graphify-enabled repo — if the flag exists, rebuild the code-only graph first
(deterministic, AST-only; filter snippet in `references/rebuild-phases.md` Phase 1 —
single source, do not re-derive). Then, from the target repo root:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/doc-management/scripts/check_design_doc_freshness.py [DOC_ROOT ...]
# default DOC_ROOT: .claude/design — or run the repo's own installed copy
```

Zero-LLM: parses each doc's frontmatter `source_commit` + `manual_edit`, collects cited
source paths from the body (same path-token style as the L2 guard), runs
`git diff --name-only <source_commit>..HEAD -- <paths>` → non-empty = **STALE** (prints
doc + changed files). Missing/empty required frontmatter keys (`type`/`topic`/
`source_commit`/`manual_edit` — the section-5 contract) = frontmatter-contract **WARN**.
`manual_edit: true` docs are skipped for freshness — automation never touches them. **Always exits
0** — this is a WARN gate; a blocking gate would hold every code PR hostage to doc
updates. Known limits: renames/moves untracked (path-based diff); cited paths are
collected only under the script's top-level path-prefix allowlist (labeled CONFIG
block, mirroring the L2 guard's; override per repo via
`DOC_FRESHNESS_PATH_PREFIXES="dir1,dir2"` env) — cites under trees outside the
allowlist are invisible and silently report fresh, so extend it when a repo grows
a new source tree.

**Per-doc refresh, for each STALE doc:**
1. Re-query the graph for the doc's topic (`graphify query`/`explain` against
   `.graphify/code-only/...`) — find what structurally changed, including sibling
   modules whose shared pages may also be stale.
2. **READ the actual source files** that changed — never patch prose from the diff
   alone.
3. Update cites + prose; untouched sections stay byte-identical (that contract keeps
   refreshes cheap and reviewable).
4. Bump frontmatter `source_commit` to current HEAD.
5. Run the repo's L2 guard — must pass before reporting.

**Scope guards:**
- **Skip dated/historical docs** (ADRs, `docs/audit/*`, dated plans) — they record
  what was true then; rewriting them is revisionism.
- **Batch threshold:** refreshes touching ≥5 docs or any governance/rules page go
  through dual adversarial review before landing. Below that, a single reviewed PR.
- **Escalation:** if the stale set exceeds ~30% of the doc tree, STOP patching and run
  REBUILD Phase 0 — at that scale the tree's organizing structure is stale, not just
  its facts.
- Optional sync state (useful in busy repos): `.planning/doc-sync/last-sync.json`
  recording `last_sync_commit` + per-doc covered-modules map; update entries in place.
  The frontmatter `source_commit` contract is the SoT — the state file is an index,
  not a second truth.

**FORBIDDEN: full-auto LLM rewrite + auto-commit.** Detection is automatic; every
refresh lands through review. Committing/merging follows the repo's own governance
(deploy-boundary check before any docs-only merge).

## MODE: AUDIT — read-only evidence fan-out

Finds what machines can't: prose that lies about current logic. Full methodology +
copy-paste auditor prompt template: **`references/audit-methodology.md`**.

**Core discipline — evidence over docs.** A doc is a claim, not truth. Evidence
precedence, highest first: **code > tests > CLI/--help > config/migrations/schemas >
generated artifacts > logs**; historical docs are LEADS ONLY, never proof. Never mark a
claim true because another doc says so.

**Flow:**
1. **Scope** — change-driven (default: docs covering code changed since the last
   audit), full sweep, or comments-first. Establish ground truth first: read CLAUDE.md
   / docs index / rules, build the known-recent-changes list from git log + memory.
2. **Fan-out** — N parallel READ-ONLY agents, one per change-area, each given the
   known recent changes, exact scope, classification rule, and evidence precedence
   (template in the reference). Classification per claim:
   - `STALE-AS-CURRENT` (bad — fix): describes a removed/changed mechanism as current.
   - `CORRECT-HISTORICAL` (leave): explicitly records the removal.
   - `CORRECT-CURRENT` (leave).
3. **Consolidate** — merge into one ranked P0/P1/P2 table (P0 = actively misleading);
   collapse to root causes (most findings trace to a few: a deleted file still
   referenced, a renamed symbol, a demoted module). Present for approval.
4. **Fix → delegate to MAINTAIN** — approved fixes run as MAINTAIN per-doc refreshes
   (same review rules, same skip-historical rule). AUDIT itself never writes.
5. **Lock** — if the repo lacks the L2 guard, install the bundled
   `scripts/check-doc-reference-integrity.mjs` (copy from
   `${CLAUDE_PLUGIN_ROOT}/skills/doc-management/scripts/`, edit the CONFIG block, wire
   into the doc-check/CI step; instructions in the reference) so the mechanical class
   can't silently return.

Report honestly: per-severity counts + root causes + what was skipped and why +
residual semantic risk. Never "docs now perfect".

## Anti-re-rot stack (what runs when)

| Layer | Catches | Trigger | Blocks? |
|-------|---------|---------|---------|
| L1 generate (`--check` freshness on OpenAPI-style exports) | fact drift in generated artifacts | gate | yes |
| L2 guard (`check-doc-reference-integrity.mjs`) | dead paths, `file:NNN` > EOF, retired symbols as current | gate (CI) | yes |
| graph hook (`graphify hook install` + `${CLAUDE_PLUGIN_ROOT}/hooks/doc-sync-update.sh`) | structure lag | every commit / edit | auto |
| L3 freshness (`check_design_doc_freshness.py`) | design docs whose cited sources changed | gate WARN + post-commit line | **WARN only** |
| MAINTAIN | resolving STALE | on-demand batch | reviewed |
| AUDIT | semantic drift (prose ↔ logic) | periodic / post-big-refactor | report |

## claim-ledger: retired (do not reintroduce)

The hand-maintained claim-ledger JSON (per-claim `status` + manual `last_verified`
bumps) is itself a hand-maintained-doc rot pattern — the exact disease this system
treats. **Replacement: L3 SHA freshness** (deterministic staleness detection per doc)
**+ AUDIT** (evidence-backed claim verification on demand). Load-bearing claims are
verified during AUDIT and recorded as findings, not as a parallel ledger artifact that
itself needs maintenance.

## Bundled assets

- `scripts/check_design_doc_freshness.py` — L3 freshness checker (zero-LLM, WARN-only,
  exit 0 always). Copy into the target repo's scripts dir or run from the skill.
- `scripts/check-doc-reference-integrity.mjs` — L2 deterministic guard
  (project-agnostic, Node built-ins only). Copy in, edit the CONFIG block, wire into
  CI. Parses all real-world anchor styles incl. `file.py:33,36,37` comma lists.
- `references/doc-management-system.md` — canonical system spec (3-layer model,
  contracts, automation table, known limits). The Why behind every rule here.
- `references/rebuild-phases.md` — full REBUILD procedure (7 phases, discovery slots,
  code-only filter snippet, red-flag table).
- `references/audit-methodology.md` — full AUDIT methodology (auditor prompt template,
  evidence rules, guard install steps, anti-patterns).

## Verification checklist (any mode, before reporting)

- [ ] Mode chosen via the routing table; REBUILD only after a `patchwork` verdict.
- [ ] Structure facts queried from the code-only graph, never hand-mirrored.
- [ ] Every refreshed/authored doc written after READING the source it cites.
- [ ] Historical/dated docs left intact; `manual_edit: true` docs untouched.
- [ ] L2 guard green; freshness script run (WARN count reported, not hidden).
- [ ] Batches ≥ threshold went through dual adversarial review.
- [ ] No full-auto rewrite + auto-commit anywhere in the run.
- [ ] Report lists per-severity counts, skips + reasons, residual risk — no
      "100/100" / "완벽" / "최종" self-assessment.
