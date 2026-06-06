---
description: "Run in any project directory to: scan code + docs, auto-fix drift, verify against rubric, export to Obsidian + NotebookLM + graphify. Single command. Upsert semantics — existing Obsidian vault / NotebookLM notebook updated; missing ones created."
argument-hint: "--source <code|notebooklm|api_kb> <vault_path> [--input <repo_path>] [--rubric <file>] [--dry-run]"
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task]
---

# /vault-build

Universal project documentation pipeline. Run in CWD.

## Usage

```
/vault-build                                    # full pipeline in CWD
/vault-build /path/to/project                   # explicit project path
/vault-build --dry-run                          # scan + drift report only
/vault-build --no-fix                           # skip drift fix (read-only)
/vault-build --export obsidian,notebooklm       # subset of destinations
/vault-build --export obsidian                  # single destination
/vault-build --export obsidian,bases,canvas     # kepano dashboards + graph canvas
/vault-build --auto-graphify                    # post-export: graphify update + global add
/vault-build --auto-graphify --no-global        # auto-graphify but skip global merge
/vault-build --global-tag <tag>                 # rename project in global graph
/vault-build --rubric ./custom.yaml             # override rubric
/vault-build --doc-root ./alt-docs              # docs live elsewhere
/vault-build --obsidian-path ~/MyVaults         # override default vault location
/vault-build --project-name custom-name         # override (default = directory name)
```

## Pipeline (5 phases)

```
[1/5] Scan         code AST + existing markdown → unified state
[2/5] Drift        cross-reference → 4 drift types (gap / orphan / claim / symbol)
[3/5] Fix          PM dispatches gap-filler / orphan-pruner / drift-fixer in parallel
                   (skip if --no-fix; skip pages with manual_edit: true)
[4/5] Verify       rubric.yaml acceptance rules → score per dim, fail closed
                   if <pass_threshold, PM re-dispatches with critique (≤3 retry)
[5/5] Export       Up to 5 destinations (upsert: update existing, create if missing)
                   - obsidian   → ~/Documents/Obsidian/<project>/
                   - notebooklm → notebook titled <project>
                   - graphify   → <project>/.vault-builder/graphify-out/
                   - bases      → <vault>/meta/bases/{sources,concepts,entities,manual-edited}.base
                   - canvas     → <vault>/meta/graph-hub.canvas (top 80 god_nodes)
                   (+ optional --auto-graphify: graphify update + global add)
```

## Outputs

In project root:
- `.vault-builder/drift-report.{md,json}` — Phase 2 output
- `.vault-builder/fix-plan.json` — Phase 3 ticket plan
- `.vault-builder/verify-report.md` — Phase 4 rubric score
- `.vault-builder/export-report.json` — Phase 5 destination summary
- `.vault-builder/state.json` — unified state across phases (source_sha, last_run_ts)
- `.vault-builder/gap-filler-actions.md`, `orphan-pruner-actions.md`, `drift-fixer-actions.md` — worker logs

In docs/:
- Auto-fixed pages (frontmatter `last_synced`, `manual_edit: false`)
- New pages under `docs/modules/` for gap items

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
- `sources.base`, `concepts.base`, `entities.base`, `manual-edited.base` — kepano Obsidian Bases dashboards. Multi-source / manual-edit filters built in.

In `<vault>/meta/graph-hub.canvas` (when `--export` includes `canvas`):
- JSON Canvas with the top 80 god_nodes laid out in a grid + every edge that connects two top-N nodes.

When `--auto-graphify` is set:
- Runs `graphify update <repo>` (or `graphify extract --no-cluster` for first run).
- Then `graphify global add <repo>/graphify-out/graph.json --as <tag>` (skip with `--no-global`).
- `<tag>` defaults to the repo directory name; override via `--global-tag`.

## Execution (Claude follows these steps)

```bash
PROJECT="${1:-$PWD}"
ROOT="${CLAUDE_PLUGIN_ROOT}"

# Phase 1-2: scan + drift
python3 "$ROOT/pipeline/drift.py" "$PROJECT" --out "$PROJECT/.vault-builder/drift-report.md"

# Phase 3: prepare ticket plan (read by PM)
python3 "$ROOT/pipeline/fix.py"   "$PROJECT" --out "$PROJECT/.vault-builder/fix-plan.json"
python3 "$ROOT/pipeline/dispatch.py" "$PROJECT" load-plan   # creates dispatch-state.json
```

**Phase 3.5 — PM dispatch** (Claude invokes Agent tool):

```
Agent(
  subagent_type="general-purpose",
  description="PM orchestrator drift-fix",
  prompt=f"""Read {CLAUDE_PLUGIN_ROOT}/agents/pm-orchestrator.md and follow the
  'Drift-fix mode' workflow on project {PROJECT}.

  1. Call `python3 {CLAUDE_PLUGIN_ROOT}/pipeline/dispatch.py {PROJECT} list-pending`
  2. Dispatch every pending ticket in parallel via Agent tool (single message, multiple tool_use blocks)
  3. After workers reply, mark each delivered; run verify-all
  4. Reissue rejected (≤3 strikes); escalate after
  5. Final rubric check: python3 {CLAUDE_PLUGIN_ROOT}/pipeline/verify.py {PROJECT}
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

If `--no-fix`: skip Phase 3.5 (PM) entirely; verify + export run on as-is docs.
If `--dry-run`: stop after Phase 2 (drift report only).

## Idempotency

- All phases re-runnable.
- `state.json` records `source_sha` (hash of code+docs). If unchanged, plug skips Phases 2-4.
- Manual-edit pages (frontmatter `manual_edit: true`) never touched by Phases 3 or 5.

## Validated

ga4-collector: 103 modules / 23 docs → 8 gap + 24 orphan + 11 claim_drift detected. (Phase 3+ pending PM dispatch wiring.)
