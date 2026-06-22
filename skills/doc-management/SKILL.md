---
name: doc-management
description: >-
  THE docs subsystem — one skill, three modes (REBUILD / MAINTAIN / AUDIT) that keeps a
  repo's documentation matching its code, graphify-native. Use when: "doc rot", "문서
  개판", "docs don't match code", "문서 전면 재작성", "rebuild docs from code",
  "graphify-native docs", patchwork doc tree after a big refactor/migration (→ REBUILD);
  "doc sync", "문서 동기화", "docs behind code", "incremental doc update", "코드 바뀐
  만큼만 문서 갱신", stale design docs after merging a feature, "bootstrap frontmatter",
  "stamp docs with source_commit", "sentinel merge", "preserve user edits in vault",
  "incremental vault refresh" (→ MAINTAIN); "doc drift", "문서 최신화", "docs audit",
  "주석이 옛날 정책", "sync docs to the codebase", docs that may be aspirational or
  agent-written and need verification (→ AUDIT). Requests for a "claim ledger" also land
  here — that pattern is retired; SHA freshness + AUDIT replace it. NOT for:
  Obsidian/NotebookLM vault export (vault-build), harness bootstrap (setup-harness),
  whole-codebase quality scoring (adversarial-review-loop), DB-schema / env-config drift.
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
frontmatter contract, automation table (L1/L2/L3), and known limits. Onboarding output
contract: `references/onboarding-hub.md`. Read both before changing how any mode works.
This SKILL.md is the executable entry.

## Mode routing — pick first

| Symptom | Mode |
|---|---|
| Tree rotten/patchwork; structure hand-typed; per-module wikis drifting; stale policies described as current | **REBUILD** — demolish + reauthor from the graph |
| Tree healthy; code changed since docs were written; freshness script reports STALE | **MAINTAIN** — targeted per-doc refresh |
| Prose may lie about logic; docs possibly aspirational/agent-written; post-refactor truth check | **AUDIT** — read-only evidence fan-out |
| Export docs/graph to an Obsidian / NotebookLM vault | NOT here → `vault-build` |

AUDIT finds, MAINTAIN fixes, REBUILD replaces. Steady-state lifecycle: REBUILD once →
post-commit hook keeps the graph fresh → `check_design_doc_freshness.py` flags stale docs (blocking)
→ MAINTAIN batches the refreshes → periodic AUDIT catches what machines can't.
"The user thinks it's rotten" is a hypothesis, not a finding — REBUILD's Phase 0
diagnosis decides between full rebuild and targeted cleanup; when in doubt start there.

## Gotchas (hard-won — read BEFORE running any mode)

**Read `references/gotchas.md` first** — 17 incident-backed gotcha→mitigation rows
(every row a real incident: graph filtering, cite rot, Why-harvest ordering,
machine-read docs, deploy governance, review discipline, claim-ledger retirement).
That file is the source of truth; nothing here duplicates it.

## The 3-layer model (shared by all modes)

| Layer | Source of truth | Drift defense |
|-------|-----------------|---------------|
| **What** — modules, calls, deps | code graph (graphify Tree-sitter AST, **code-only filter**); consume via `graphify query/explain` | regenerated from code; post-commit hook |
| **Why** — decisions, incidents, gotchas, governance | `intent/` layer (ADR/gotcha/history/governance), faithful-extraction-only, every entry cites a source, unknown = `(why not documented)` | inherently historical — doesn't rot |
| **Generated mirror** — repo `.claude/design/`, rules, nav, docs, onboarding hub | generated from the two layers above with `file:line`/symbol-anchor cites; live only after dual review | L2 guard (mechanical) + L3 SHA freshness (auto-detect) + AUDIT (semantic) |

Forbidden patterns: per-module structure pages (the rot machine) · hand-mirroring
structure facts (query the graph instead) · governance restated in N pages (single SoT
page + one-line cites) · unreviewed LLM prose going live.

## Authoring inputs — project-context resolution

Before Phase-0 diagnosis (REBUILD) or any authoring pass (MAINTAIN/AUDIT), resolve
project understanding in the 4-step order:
`skills/auto-pilot/references/project-context-resolution.md`.

## MODE: REBUILD — full demolish + reauthor

Full procedure (the proven 7-phase, end-to-end-verified on PickL-API):
**`references/rebuild-phases.md`** — read it before executing. Phase map:

0. **Diagnose (hard gate)** — parallel read-only audits → explicit `disciplined` /
   `patchwork` verdict. Only `patchwork` unlocks Phases 1–7; `disciplined` exits to
   targeted cleanup (often: delete scratch, collapse a duplicated fact, distill plans
   → ADR, fix dead refs — then STOP).
1. **Code-only product graph** — `graphify update . --force` (AST-only) → filter graph.json
   (file_type AND extension AND path excludes) → repo-rooted
   `.graphify/code-only/graphify-out/graph.json` → `cluster-only` → validate with a
   domain query (fixtures returned = filter failed).
2. **Vault workbench** — `_graph/` artifacts + `intent/` Why-harvest (cite sources,
   never invent, harvest BEFORE deleting anything).
3. **Author FROM the graph** — one agent per subsystem (~8-10 topic docs, NOT
   per-module): query → READ the actual source surfaced → write with cites + Why.
4. **Rewrite the repo trees, clean-slate** — only rewritten+reviewed docs go live;
   everything else → `_archive/` (frozen, guard-exempt, future verified-extraction
   source). Root docs (README / CLAUDE.md / AGENTS.md / OVERVIEW / docs-index) and the
   AI/developer onboarding hub get a fresh rewrite against the new structure. Live exceptions: GENERATED artifacts +
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

## MODE: MAINTAIN — incremental code→docs→vault refresh

The steady-state mode. Detection is automatic (zero-LLM); refresh is reviewed.
Vault push happens via `vault-sync.sh` (now sentinel-aware) on deploy — not here.

**Step 0 — bootstrap frontmatter (if any docs lack it).**
Run once before freshness detection; idempotent:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/doc-management/scripts/bootstrap_frontmatter.py --write [DOC_ROOT ...]
```
Injects `type` / `topic` / `source_commit` / `manual_edit` from path heuristics + HEAD sha.
Skips docs already carrying all 4 keys. Docs with `manual_edit: true` are never touched.

**CAVEAT:** bootstrap stamps `source_commit=HEAD`, which tells the L3 freshness
gate "this doc is accurate as of HEAD". Run bootstrap only AFTER an AUDIT pass
(or on docs you have just verified) — bootstrapping unaudited/stale docs silently
marks them as fresh and masks real drift until the next code change touches their
cited paths.

**Step 1 — detect STALE set.**
The graph-freshness watcher (`${CLAUDE_PLUGIN_ROOT}/hooks/doc-sync-update.sh`,
PostToolUse) marks `graphify-out/needs_update` when code is edited — if the flag
exists, rebuild the code-only graph first (filter snippet in
`references/rebuild-phases.md` Phase 1 — single source, do not re-derive). Then:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/doc-management/scripts/check_design_doc_freshness.py [DOC_ROOT ...]
# default DOC_ROOT: docs — or run the repo's own installed copy
```
Zero-LLM: per doc, diffs cited source paths against frontmatter `source_commit`
(`git diff --name-only <commit>..HEAD -- <paths>`) → non-empty = **STALE** (exit 1).
Missing required frontmatter keys = frontmatter-contract **WARN** (exit 0, advisory).
Known limits: renames/moves untracked; cites only under the path-prefix allowlist
(CONFIG block / `DOC_FRESHNESS_PATH_PREFIXES` env).

**Step 2 — expand impact set.**
For each changed source file that caused STALE, expand to sibling/dependent docs:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/doc-management/scripts/affected_docs.py   --doc-root docs [CHANGED_FILE ...]
```
Runs `graphify affected <symbol>` per file (basename fallback when graphify absent);
greps DOC_ROOT for docs citing any affected symbol. Union with the Step 1 STALE set
= full refresh target list.

**Step 3 — regenerate each doc in the refresh set.**
For each doc in the union set:
0. If docs structure or first-read paths are affected, update the onboarding hub
   (`references/onboarding-hub.md`) before reporting completion.
1. Re-query the graph (`graphify query`/`explain` against `.graphify/code-only/...`)
   — find what structurally changed.
2. **READ the actual source files** that changed — never patch prose from the diff
   alone.
3. Wrap machine-owned prose in `<!-- @generated --> ... <!-- /@generated -->` sentinels;
   leave existing `<!-- @user --> ... <!-- /@user -->` regions untouched (they are
   human-owned — see `references/doc-management-system.md §10`).
4. Write via `sentinel_merge.py` to preserve `@user` blocks:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/doc-management/scripts/sentinel_merge.py      <existing_doc> <new_generated_doc> --out <existing_doc>
   ```
5. Bump frontmatter `source_commit` to current HEAD.
6. Run the repo's L2 guard — must pass before reporting.

**Step 4 — note on vault push.**
The Obsidian vault mirror is updated automatically via `~/.claude/scripts/vault-sync.sh`
on the next deploy. That script now calls `sentinel_merge` per doc, so `@user` edits
made directly in the vault are preserved across deploys. No manual vault action needed
here.

**Scope guards:**
- **Skip dated/historical docs** (ADRs, `docs/audit/*`, dated plans) — they record
  what was true then; rewriting them is revisionism.
- **Batch threshold:** refreshes touching ≥5 docs or any governance/rules page go
  through dual adversarial review before landing. Below that, a single reviewed PR.
- **Escalation:** if the stale set exceeds ~30% of the doc tree, STOP patching and run
  REBUILD Phase 0 — at that scale the tree's organizing structure is stale, not just
  its facts.
- Optional sync-state index for busy repos: `.planning/doc-sync/last-sync.json`
  (`last_sync_commit` + per-doc covered-modules map, updated in place) — the
  frontmatter `source_commit` contract stays the SoT; the state file is never a
  second truth.

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
| L3 freshness (`check_design_doc_freshness.py`) | design docs whose cited sources changed | gate STALE-blocking (exit 1) + post-commit line | **STALE blocks** (exit 1); frontmatter-contract WARN advisory (exit 0) |
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

- `scripts/check_design_doc_freshness.py` — L3 freshness checker (zero-LLM, STALE blocks
  exit 1; frontmatter-contract WARN advisory exit 0). Copy into target repo or run from skill.
- `scripts/bootstrap_frontmatter.py` — inject missing frontmatter (type/topic/source_commit/
  manual_edit) into docs lacking it. Dry-run by default; `--write` to apply. Idempotent.
- `scripts/affected_docs.py` — expand changed-source-file list to full doc refresh impact
  set via graphify affected + grep. Stdin or args; falls back to basename when graphify absent.
- `scripts/sentinel_merge.py` — merge engine preserving `<!-- @user -->` blocks across
  generated doc updates. CLI: `sentinel_merge.py <existing> <generated> [--out PATH]`.
- `scripts/install_doc_hooks.sh` — installs LOCAL git hooks (post-commit advisory +
  pre-push blocking freshness gate) into the current repo. Idempotent, no global install.
- `scripts/check-doc-reference-integrity.mjs` — L2 deterministic guard (project-agnostic,
  Node built-ins only). Copy in, edit CONFIG block, wire into CI.
- `references/doc-management-system.md` — canonical system spec (3-layer model, contracts,
  automation table, sentinel convention §10, known limits). The Why behind every rule here.
- `references/gotchas.md` — 17 incident-backed gotcha→mitigation rows (single source; read
  before running any mode).
- `references/onboarding-hub.md` — AI / Developer onboarding hub contract.
- `references/rebuild-phases.md` — full REBUILD procedure (7 phases, discovery slots,
  code-only filter snippet, red-flag table).
- `references/audit-methodology.md` — full AUDIT methodology (auditor prompt template,
  evidence rules, guard install steps, anti-patterns).
- `evals/evals.json` — skill-creator eval cases (bootstrap+detect, sentinel merge, affected
  docs selection); `passed: false` placeholders for the eval loop to fill.

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
