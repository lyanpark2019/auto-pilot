---
type: generated-mirror
topic: AI / Developer onboarding hub
source_commit: 6b7d869
manual_edit: false
---

# AI / Developer onboarding hub

Use this page when you are new to auto-pilot or when an AI agent needs project context before changing anything.

## Rule 0 — do not guess the architecture

- `What` comes from current code and the graph.
- `Why` comes from architecture docs, asset charters, ADR-like history, and retros.
- Old docs are leads, not proof. If a doc and graph disagree, read the source before editing.

## Persistent LLM wiki pattern

This hub follows the LLM Wiki pattern: maintain a **persistent, compounding wiki** instead of rediscovering context from scratch in every chat.

| Layer | auto-pilot mapping | Rule |
|---|---|---|
| Raw sources | repo source, specs, review logs, CI logs, vault raw/source notes | Immutable evidence; read before trusting prose. |
| Generated wiki | `docs/`, `graphify-out/`, Knowledge vault project pages | LLM-maintained synthesis; useful but always freshness-checked. |
| Schema | `CLAUDE.md`, `docs/README.md`, this hub, skill references | Tells agents how to maintain and query the wiki. |

Operations:

- **Ingest:** add new verified evidence to docs/vault only after source-backed review.
- **Query:** answer architecture questions from `index.md`/hub pages plus graphify queries, then file durable answers back into docs when reusable.
- **Lint:** periodically check contradictions, stale claims, orphan pages, missing cross-links, and graph freshness.
- **Log:** keep chronological evidence in commit history, review reports, retro notes, and vault logs; a `log.md` is optional for project vaults that need a human-readable timeline.

## 10-minute architecture map

1. **Product purpose:** auto-pilot is a Claude Code plugin for brownfield, spec-driven development. It is not application code.
2. **Core loop:** PM plans contracts → workers edit in isolated worktrees → Codex + cold Claude review frozen diffs → gates verify → PM merges/commits.
3. **Four pillars:** autonomous coding loop, doc freshness, persistent knowledge, and safety/enforcement.
4. **State:** `.planning/auto-pilot/state.json` is written through `scripts/_state.py`; worker contracts live under `.planning/auto-pilot/contracts/`.
5. **Main-tree mutation:** worker changes should flow through `WorktreeManager.apply_to_main`; direct root edits are exceptional and guarded.
6. **Docs:** `doc-management` owns repo docs REBUILD/MAINTAIN/AUDIT. `/vault-build` owns Obsidian/NotebookLM export only.
7. **Quality:** `adversarial-review-loop` owns branch review, codebase scoring, and lifecycle quality loops.

## First-read path

1. `README.md` — routing table and install/use overview.
2. `docs/README.md` — docs map and source-of-truth order.
3. `docs/architecture.md` — system anatomy, contracts, state, worktrees, reviewers.
4. `docs/asset-charter.md` — which asset owns which capability.
5. `CLAUDE.md` — repo-specific development rules and verification commands.
6. Task-specific owner:
   - Feature/spec work: `skills/auto-pilot/SKILL.md`, `agents/pm-orchestrator.md`.
   - Review/quality: `skills/adversarial-review-loop/SKILL.md`, `skills/quality-eval/SKILL.md`.
   - Docs: `skills/doc-management/SKILL.md`.
   - Vault export: `commands/vault-build.md`, `commands/vault-score.md`.

## Graphify context workflow

Before broad source scans, check graph freshness:

```bash
git rev-parse --short HEAD
rg -n "Built from commit" graphify-out/GRAPH_REPORT.md
graphify update . --force
```

Use scoped graph queries from the checked query suite (`scripts/graphify_query_suite.json`):

```bash
graphify query "WorktreeManager apply_to_main collect_patches cleanup main_apply_lock" --graph graphify-out/graph.json --budget 1400
graphify query "collect_round_outcome read_review done marker schema validate" --graph graphify-out/graph.json --budget 1400
graphify explain "WorktreeManager" --graph graphify-out/graph.json
graphify explain "run_query_suite()" --graph graphify-out/graph.json
graphify path "export_obsidian()" "_write_index()" --graph graphify-out/graph.json
graphify affected "collect_round_outcome()" --graph graphify-out/graph.json --depth 1
```

Use `graphify extract . --mode deep` only when you need a full headless semantic rebuild. For normal code changes, `graphify update . --force` is the no-LLM refresh path.

## Task routing

| Need | Owner |
|---|---|
| Build from a phased spec | `/auto-pilot` or `/auto-pilot-server` |
| Parallel worker pool | `swarm` skill |
| Branch/diff review | `adversarial-review-loop` branch mode |
| Whole-codebase score/fix | `adversarial-review-loop` codebase mode |
| Dead code or residue | `residue-audit` |
| Repo docs stale or misleading | `doc-management` AUDIT → MAINTAIN |
| Full docs rebuild | `doc-management` REBUILD after patchwork verdict |
| Obsidian/NotebookLM export | `/vault-build`, then `/vault-score` |
| SHA-pinned deploy standard | `sha-deploy-standard` |

## Maintenance safety checklist

- Confirm the owner skill/agent before editing.
- Use graphify for current structure facts, then read the source it points at.
- Preserve clearly historical `Why`; do not rewrite dated plans as current truth.
- Do not add a new skill/agent when an existing owner covers the job.
- Keep skill markdown gotchas-first and under the module-size budget.
- Put plugin-internal paths in command/skill markdown behind `${CLAUDE_PLUGIN_ROOT}` when they must run after install.
- Run the local checks named in `CLAUDE.md` before claiming completion.

## Verification quickstart

For docs-only work:

```bash
python3 scripts/docs/check_doc_reference_integrity.py
python3 -m pytest tests/test_doc_reference_integrity.py -q
git diff --check
```

For code or gate changes, use the full `CLAUDE.md` verification list. For graph/vault changes, also run:

```bash
python3 scripts/graphify_vault_loop.py --vault /Users/lyan/Documents/Knowledge/wiki/projects/auto-pilot --compact --max-iterations 1
```

## Common onboarding traps

| Trap | Safer move |
|---|---|
| Starting from stale generated graph notes | Run `graphify update . --force`; compare `GRAPH_REPORT.md` built commit to HEAD. |
| Treating old docs as current implementation | Classify as `Why` unless graph + source confirm current `What`. |
| Reading every file manually first | Ask a graphify query, then read only surfaced files. |
| Confusing repo docs with vault export | Use `doc-management` for repo docs; use `/vault-build` for Obsidian/NotebookLM export. |
| Adding a new asset for an existing capability | Check `docs/asset-charter.md` and README routing first. |
