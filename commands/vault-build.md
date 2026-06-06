---
name: vault-build
description: "Export pipeline: build/update an Obsidian vault + NotebookLM notebook + graphify output (and optional bases/canvas dashboards) from a project. Upsert semantics — existing vault/notebook updated, missing ones created. Repo-docs drift-fix/scoring is RETIRED here (→ doc-management skill); it runs only with the explicit --fix-repo-docs opt-in."
argument-hint: "[<project_path>] [--export obsidian,notebooklm,graphify,bases,canvas] [--source <code|notebooklm|api_kb>] [--fix-repo-docs] [--dry-run]"
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task]
---

# /vault-build

> **Repo-docs doc-purpose path RETIRED.** Detecting/fixing/scoring a repo's own
> `docs/` tree (`--source code` drift → fix → rubric as the goal) belongs to the
> **`doc-management`** skill (REBUILD / MAINTAIN / AUDIT modes) — it is NOT part of
> this command's default flow. If the user asks `/vault-build` to fix or score the
> repo's own docs **without** `--fix-repo-docs`, STOP and route them to
> `doc-management` instead of running Phases 2-4. `/vault-build` is the **export
> pipeline**: building/updating Obsidian vaults, NotebookLM notebooks, bases,
> canvas, and graphify output. NotebookLM/knowledge-vault building stays fully
> functional — every doc-purpose path (drift/fix/rubric on a repo's own docs) is
> deprecated with this pointer. Canonical mapping: doc-용도 제거, export 잔류.

## Usage

```
/vault-build                                    # EXPORT-ONLY (default): obsidian,notebooklm,graphify
/vault-build /path/to/project                   # explicit project path
/vault-build --export obsidian,notebooklm       # subset of destinations
/vault-build --export obsidian,bases,canvas     # kepano dashboards + graph canvas
/vault-build --auto-graphify                    # post-export: graphify update + global add
/vault-build --auto-graphify --no-global        # auto-graphify but skip global merge
/vault-build --global-tag <tag>                 # rename project in global graph
/vault-build --doc-root ./alt-docs              # docs live elsewhere
/vault-build --obsidian-path ~/MyVaults         # override default vault location
/vault-build --project-name custom-name         # override (default = directory name)
/vault-build --source notebooklm                # build a knowledge vault FROM NotebookLM sources
                                                #   (vault-internal flow; alias: /nbm-to-obsidian)

# RETIRED path — explicit opt-in ONLY (otherwise use the doc-management skill):
/vault-build --fix-repo-docs                    # legacy Phases 2-4: drift → fix → rubric on repo docs/
/vault-build --fix-repo-docs --dry-run          # drift report only, no mutations
/vault-build --fix-repo-docs --rubric ./custom.yaml
```

## Pipeline

**Default (export-only) — 2 phases:**

```
[1/2] Scan         light state refresh (.vault-builder/state.json: source_sha, source_adapter)
[2/2] Export       up to 5 destinations (upsert: update existing, create if missing)
                   - obsidian   → ~/Documents/Obsidian/<project>/
                   - notebooklm → notebook titled <project>
                   - graphify   → <project>/.vault-builder/graphify-out/
                   - bases      → <vault>/meta/bases/{sources,concepts,entities,manual-edited}.base
                   - canvas     → <vault>/meta/graph-hub.canvas (top 80 god_nodes)
                   (+ optional --auto-graphify: graphify update + global add)
```

**Opt-in `--fix-repo-docs` (RETIRED doc-purpose path — kept for legacy/vault-internal use only, never the default):**

```
[2/5] Drift        cross-reference code AST ↔ docs → 4 drift types (gap/orphan/claim/symbol)
[3/5] Fix          PM dispatches gap-filler / orphan-pruner / drift-fixer in parallel
                   (skip pages with manual_edit: true)
[4/5] Verify       rubric.yaml acceptance rules → score per dim; <pass_threshold →
                   PM re-dispatches with critique (≤3 retry)
```

⚠️ These phases generate/rewrite pages in the target's `docs/` tree (including new
`docs/modules/` pages for gap items) — the unreviewed per-module generation pattern
that doc-management forbids for a repo's own docs. Use them only for vault-internal
content (`--source notebooklm|api_kb`) or when the user explicitly accepts the
legacy behavior; the supported repo-docs path is the `doc-management` skill.

## Outputs

Default (export-only), in project root `.vault-builder/`:
- `export-report.json` — per-destination summary (failures exit non-zero; graceful
  skips, e.g. missing `notebooklm` CLI, stay rc=0 with `"skipped": true`)
- `state.json` — unified state (source_sha, source_adapter, last_run_ts)

In `~/Documents/Obsidian/<project>/`:
- Mirror of `docs/` + top-level `README.md`/`CLAUDE.md`/`AGENTS.md`/`ARCHITECTURE.md`
- Auto-generated `index.md` listing all pages
- Existing `manual_edit: true` pages preserved (not overwritten)

In NotebookLM:
- Notebook named `<project>` (existing notebook reused; created if absent)
- Sources synced (markdown files added; existing matched by relative path)

In graphify-out:
- `graph.json`, `GRAPH_REPORT.md` etc — output of `graphify extract docs/ --no-cluster`
- (`graphify build` was removed upstream; the current contract is `extract`.)

In `<vault>/meta/bases/` (when `--export` includes `bases`):
- `sources.base`, `concepts.base`, `entities.base`, `manual-edited.base` — kepano
  Obsidian Bases dashboards. Multi-source / manual-edit filters built in.

In `<vault>/meta/graph-hub.canvas` (when `--export` includes `canvas`):
- JSON Canvas: top 80 god_nodes in a grid + every edge connecting two top-N nodes.

When `--auto-graphify` is set:
- Runs `graphify update <repo>` (or `graphify extract --no-cluster` for first run).
- Then `graphify global add <repo>/graphify-out/graph.json --as <tag>` (skip with
  `--no-global`). `<tag>` defaults to the repo directory name; override `--global-tag`.

Only with `--fix-repo-docs` (additionally):
- `.vault-builder/drift-report.{md,json}`, `fix-plan.json`, `verify-report.md`
- `.vault-builder/{gap-filler,orphan-pruner,drift-fixer}-actions.md` — worker logs
- Auto-fixed pages in docs/ (frontmatter `last_synced`, `manual_edit: false`) +
  new pages under `docs/modules/` for gap items (see the ⚠️ above)

## Execution (Claude follows these steps)

```bash
PROJECT="${1:-$PWD}"
ROOT="${CLAUDE_PLUGIN_ROOT}/vault"
```

**Default flow (no `--fix-repo-docs`) — export only:**

```bash
python3 "$ROOT/pipeline/export.py" "$PROJECT" \
    --export "${EXPORTS:-obsidian,notebooklm,graphify}" \
    --out "$PROJECT/.vault-builder/export-report.json"
# Non-zero exit = at least one destination FAILED (see report); "skipped" entries are fine.
```

If the user's actual goal is "fix/refresh the repo's own docs", do NOT proceed —
invoke the `doc-management` skill (MAINTAIN for targeted refresh, AUDIT for drift
findings, REBUILD for clean-slate) and stop here.

**Opt-in flow (`--fix-repo-docs` explicitly passed):**

```bash
# Phase 1-2: scan + drift
python3 "$ROOT/pipeline/drift.py" "$PROJECT" --out "$PROJECT/.vault-builder/drift-report.md"
# --dry-run stops here (drift report only)

# Phase 3: prepare ticket plan (read by PM)
python3 "$ROOT/pipeline/fix.py"   "$PROJECT" --out "$PROJECT/.vault-builder/fix-plan.json"
python3 "$ROOT/pipeline/dispatch.py" "$PROJECT" load-plan   # creates dispatch-state.json
```

**Phase 3.5 — PM dispatch** (Claude invokes Agent tool):

```
Agent(
  subagent_type="general-purpose",
  description="PM orchestrator drift-fix",
  prompt=f"""Read {CLAUDE_PLUGIN_ROOT}/agents/vault-pm-orchestrator.md and follow the
  'Drift-fix mode' workflow on project {PROJECT}.

  1. Call `python3 {CLAUDE_PLUGIN_ROOT}/vault/pipeline/dispatch.py {PROJECT} list-pending`
  2. Dispatch every pending ticket in parallel via Agent tool (single message, multiple tool_use blocks)
  3. After workers reply, mark each delivered; run verify-all
  4. Reissue rejected (≤3 strikes); escalate after
  5. Final rubric check: python3 {CLAUDE_PLUGIN_ROOT}/vault/pipeline/verify.py {PROJECT}
  6. Report final state (round count, pass/fail, escalations)
  """
)
```

Phase 4-5 after PM exits with success:

```bash
# Phase 4 verify (PM should have hit pass already, but record final)
python3 "$ROOT/pipeline/verify.py" "$PROJECT" --out "$PROJECT/.vault-builder/verify-report.md"

# Phase 5 export — only when verify passes
python3 "$ROOT/pipeline/export.py" "$PROJECT" \
    --export "${EXPORTS:-obsidian,notebooklm,graphify}" \
    --out "$PROJECT/.vault-builder/export-report.json"
```

## Idempotency

- All phases re-runnable; export is upsert (update existing, create if missing).
- `state.json` records `source_sha` (hash of code+docs). With `--fix-repo-docs`,
  unchanged `source_sha` skips Phases 2-4.
- Manual-edit pages (frontmatter `manual_edit: true`) never touched by fix or export.

## Validated

ga4-collector: 103 modules / 23 docs → 8 gap + 24 orphan + 11 claim_drift detected
(legacy `--fix-repo-docs` path; Phase 3+ pending PM dispatch wiring). Export layer:
script-mode smoke + upsert covered by `vault/tests/test_fix_verify_export.py`.
