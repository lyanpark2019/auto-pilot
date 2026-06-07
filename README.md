# auto-pilot

Unified automated AI coding system for Claude Code. Core: a self-driving development loop — Opus 4.7 PM + Sonnet 4.6 (1M) parallel workers + Codex/Claude dual adversarial review + phase verify gates, full auto, no confirms. Around it: quality lift, harness bootstrap, graphify-native doc management (flagship), a swarm tmux parallel backend, a SHA-pin deploy standard, codex conductor mode, and a vault export layer.

Built from `/insights` friction analysis on 381 sessions — every recurring failure mode is hardcoded as a guard.

New developer or AI agent? Start at `docs/onboarding/README.md`, then use `docs/README.md` for the docs map.

## Routing table — task → ONE entry point

Anti-trigger-competition map. Each job has exactly one owner; satellites are listed with their owner, not as alternatives.

| Task | Entry |
|---|---|
| Autonomous spec-driven build (phased, in-session) | `/auto-pilot` — true headless: `/auto-pilot-server` |
| Long-running parallel execution / tmux multi-worker pool / mixed Claude+Codex worker pools | `swarm` skill (`/auto-pilot:swarm <init\|start\|status\|stop\|ticket\|bench>` — bench absorbed swarm-bench 2026-06-07); swarm assets live under `swarm/`, agents `swarm-{explorer,monitor,verifier}` at top-level `agents/` |
| PR / branch dual review (Codex + cold Claude, loop until both APPROVE) | `adversarial-review-loop` (branch mode) |
| Codebase quality score + fix loop | `adversarial-review-loop` (codebase mode) |
| Full quality lifecycle: lift → adversarial bug-hunt → harness-doc sync → autonomous merge | `adversarial-review-loop --lifecycle` (absorbed pm-quality-harness-loop 2026-06-07) |
| Dead code / duplicates / residue removal | `residue-audit` |
| Architecture improvement / module boundaries | `improve-codebase-architecture` |
| Harness bootstrap (CLAUDE.md, hooks, MCP, agents, drift guards) | `setup-harness` (+ `/setup-claude-md`; `/harness` and `/harness-ops` deleted 2026-06-07 — use `bootstrap.sh`/`harness-loop.sh` directly) |
| Docs rotten / 문서 개판 / rebuild docs from code | `doc-management` (REBUILD mode) |
| Code changed, docs behind / doc sync / 문서 동기화 | `doc-management` (MAINTAIN mode — `skills/doc-management/scripts/check_design_doc_freshness.py` STALE feed) |
| Doc drift / 문서 최신화 / docs audit / claim verification | `doc-management` (AUDIT mode) |
| Vault export to Obsidian / NotebookLM / bases / canvas / dashboard | `/vault-build` (+`--restructure`/`--resume`) · `/vault-score` (+`--audit`/`--content-verify`/`--drift`) · `/vault-dashboard` · `/vault-selftest`. Vault/Obsidian/NotebookLM export is **NOT** doc-management. |
| Vault-internal drift (exported vault vs source repo) | `/vault-score --drift` — repo code↔doc drift belongs to `doc-management` (AUDIT mode) instead |
| CI/CD setup / SHA-based deploy / rollback standard | `sha-deploy-standard` skill + `/sha-deploy-init` command — templates at `deploy/templates/` |
| Conductor mode (Codex writes code, Claude plans/reviews/gates) | `codex-orchestra` — opt-in via `.codex-conductor` repo-root marker, enforced by `hooks/codex-conductor-guard.py` (registered in `hooks/hooks.json`) |
| Goal intake / long-horizon task discovery receipts | `goal-scout` / `goal-judge` / `goal-worker` global `~/.claude` agents (dispatched by plain name from the external goalbuddy skill; not bundled in this plugin) |
| Post-run retrospective → project memory | `retro` agent — PM may dispatch at phase end; appends evidence-cited lessons to the project's `.claude/insights.md` |

**Retired / deleted (do not route here):**

- `codebase-perfection-loop` — deleted (rubric provenance distilled into `quality-eval`; directory removed) → use `adversarial-review-loop` (codebase or --lifecycle mode)
- `pm-quality-harness-loop` / `swarm-bench` / `diagnosing-{llm-output-leaks,stale-runtime}` / `code-perfector` / `eval-run` — absorbed/retired 2026-06-07 → `adversarial-review-loop --lifecycle`, `swarm bench`, `diagnosing`, `residue-audit`, `/auto-pilot eval`
- `llm-wiki-architect` — deleted (per-module hand-maintained wiki = rot machine)
- `doc-drift-audit` + `graphify-doc-rebuild` + interim `doc-sync` — absorbed into `doc-management` (AUDIT / REBUILD / MAINTAIN modes); old trigger phrases preserved in its description
- claim-ledger pattern — NOT adopted (hand-maintained verification JSON rots like any hand-maintained doc); `doc-management` SHA-freshness + AUDIT replace it
- `autopilot-swarm` skill name — renamed `swarm` (legacy trigger phrases kept in the skill description)

`doc-management` bundles its L2 mechanical guard (`skills/doc-management/scripts/check-doc-reference-integrity.mjs`) and L3 freshness script (`skills/doc-management/scripts/check_design_doc_freshness.py`) as copy-into-repo assets.

Codex CLI skills (12, versioned under `codex/`): this repo is the source of truth — deploy with `codex/sync-to-codex.sh`, see `codex/README.md`.

## Principles (Nisi 2026-06)

Full statement in `CLAUDE.md`. The three that shape every contract: **evidence over trust** — worker verify reports carry a persisted log path + SHA-256, reviewers recompute the hash and re-run (mismatch = REJECT); **retro agent** — dispatchable at phase end, appends doom-loop/wasted-pattern lessons to `.claude/insights.md`; **skills are Gotchas-first, ≤500 lines** — bulk lives in `references/`.

## Binding contracts inventory

Mechanically enforced commitments. All cited paths resolve in this repo.

| # | Who | Contract | SoT |
|---|-----|----------|-----|
| ① | Worker | Schema `additionalProperties:false`, fail-closed on unknown fields | `schemas/contract.schema.json` |
| ② | Reviewer | Read-only sandbox + PM-frozen diff + structured `APPROVE`/`REJECT` output | `skills/adversarial-review-loop/references/review-core.md` |
| ③ | PM | 보고형식·금지행위 (dispatch, gate, commit — never edits code) | `agents/pm-orchestrator.md` |
| ④ | Round-2 | `schemas/preflight.schema.json` · dispatch required fields (manifest v2) · creation gate (`scripts/asset_registry_check.py`) · dispatch-manifest gate | `agents/pm-orchestrator.md §Dispatch-manifest gate` |

Asset roles and ownership: `docs/asset-charter.md`.

## Install

```bash
# 1. clone (or symlink existing checkout into Claude plugins dir)
git clone <this-repo> ~/Documents/Project/auto-pilot
ln -s ~/Documents/Project/auto-pilot ~/.claude/plugins/auto-pilot

# 2. make hooks executable
chmod +x ~/Documents/Project/auto-pilot/hooks/*.sh

# 3. restart Claude Code session — plugin loads via SessionStart hook
```

## Usage

```
/auto-pilot start                   # use newest docs/specs/*.md (interactive, one phase per turn)
/auto-pilot start --spec PATH
/auto-pilot start --max-workers 6
/auto-pilot status
/auto-pilot resume
/auto-pilot stop

# True headless infinite loop (this is the "one-click autonomous" you want):
/auto-pilot-server                  # spawn Python driver in background
# or directly:
python3 ~/.claude/plugins/auto-pilot/scripts/headless-loop.py \
  --max-iter 100 --sleep 10 \
  --max-cost-usd 50 --max-tokens 50000000 --max-concurrent-claude 4
python3 ~/.claude/plugins/auto-pilot/scripts/headless-loop.py --once   # smoke test

# Dogfood smoke harness (PR4) — runs the 2-phase smoke spec end-to-end:
./scripts/dogfood_tier1.sh          # PR1+PR2 surface only (reviewers fall back)
./scripts/dogfood_tier2.sh          # full PR3 reviewer sandbox
./scripts/dogfood_tier1.sh --check  # gate assertions only, no loop spawn
```

## Requirements

- Claude Code with Opus 4.7 access (PM session)
- Sonnet 4.6 1M-context tier (for workers via `Agent({model: "sonnet"})`)
- `codex` CLI on PATH (`brew install codex` or per Codex docs) — for adversarial reviewer
- A spec at `docs/specs/*-*.md` or `SPEC.md` with `## Phase N` headers
- A `CLAUDE.md` listing verify commands

## What it does

For each phase in the spec:

1. **Tech-critic gate** — `tech-critic-lead` rejects scope-creep contracts BEFORE workers touch code ("기능은 비용", from cc-system)
2. PM plans N non-overlapping work contracts
3. Dispatches N Sonnet 4.6 workers in 1 message (parallel) in isolated worktrees
4. Each worker edits, runs verify tee'd to a persisted log, reports diff + verify-log path + SHA-256 (hash-less reports are bounced before review; reviewers recompute the hash)
5. Dispatches reviewers in 1 message (parallel):
   - `auto-pilot-codex-reviewer` (always) — hardened pair, legacy `codex-adversarial` deleted 2026-06-07
   - `auto-pilot-claude-reviewer` cold (always) — hardened pair, legacy `claude-reviewer` deleted 2026-06-07
   - `review-gatekeeper` if runtime code touched / trust-boundary files touched (tdd-enforcer + security-reviewer merged 2026-06-07)
   - Other specialists per `agents/specialist-pool.md`
6. ALL reviewers must APPROVE — any REJECT → loop with finding
7. Hard gates inside review: scope-drift (out-of-contract files), scope-reduction (worker loosened test instead of fixing impl)
8. Runs project verify checklist (test+lint+typecheck+build)
9. Commits atomic per worker with trailers (`auto-pilot-iter`, `auto-pilot-phase`, `auto-pilot-contract`)
10. Advances phase counter
11. Until last phase verify is green → SUCCESS report

### Headless mode (true autonomous)

`/auto-pilot-server` (or `python3 scripts/headless-loop.py`) runs an outer driver that:
1. Snapshots HEAD pre-phase
2. Checks budget caps (`--max-cost-usd`, `--max-tokens`, `--max-concurrent-claude` via `pgrep`) — abort with status `cost-cap` if exceeded
3. Spawns `claude -p --dangerously-skip-permissions` with `HARNESS_HEADLESS=1` and the auto-pilot skill
4. On phase exit:
   - success → next iteration
   - timeout / fail → `git stash` any dirty $ROOT edits under `auto-pilot-iter-N-{timeout,failed}` (recoverable, not destructive); per-worktree cleanup handles in-flight work
5. Accumulates parsed cost + token totals into `state.json` for cap enforcement
6. Repeats until terminal status (`success`, `failed`, `pivot-needed`, `stopped`, `cost-cap`) or `--max-iter`

## Hard stops

- Spec's last phase verify all green → SUCCESS, exit
- Same finding repeats 3 rounds → `pivot-needed`, exit (no whack-a-mole)
- Worker timeout > 20min → kill, exit
- User: `/auto-pilot stop`

## Friction guards (auto-loaded)

- Path typos (`Valut/`, `/tmp` cwd) — preflight warning
- Edits to `__init__.py` / composition roots — blocked (set `AUTO_PILOT_FORCE_COMPOSITION_ROOT=1` to bypass)
- `claude doctor` in non-interactive shell — blocked
- Chained Cloudflare SSL changes — blocked (one at a time)
- `ruff --fix` on composition roots — blocked
- Post-deploy: zombie port check, env placeholder leak check
- Over-scoped contracts — `tech-critic-lead` rejects with reason
- Implementation without tests — `review-gatekeeper` REJECTs
- Out-of-scope edits — auto-pilot-claude-reviewer + auto-pilot-codex-reviewer REJECT on scope drift
- Reviewer writes outside `outputs/<role>/` — `hooks/pre-reviewer-write.sh` blocks (PR3)
- Phase fail leaves dirty tree — `headless-loop.py` `stash_if_dirty` (PR4 replaces destructive reset)
- Run-away cost or fork-bomb — `--max-cost-usd` / `--max-tokens` / `--max-concurrent-claude` (PR4)
- `state.json` concurrent writes — flock + atomic temp+rename (PR4)
- Spec parser `## Phase` inside code fences — ignored by `_count_phases` (PR4)

## Inspired by

- [greatSumini/cc-system](https://github.com/greatSumini/cc-system) — `run-server.py` infinite loop pattern, `tech-critic-lead`, HARNESS_HEADLESS env signal, iter-id commit trailers; auto-pilot replaces destructive rollback with recoverable stash-on-fail
- [obra/superpowers](https://github.com/obra/superpowers) — 7-phase template, TDD-first hard rule (deletes pre-test code)
- [everything-claude-code](https://github.com/JonathanRosenberg/everything-claude-code) — specialist agent pool (security/database/tdd-guide/etc.)
- [LiorCohen/sdd](https://github.com/LiorCohen/sdd) — Spec-driven development phasing
- Lessons from `/insights` (381 sessions over 14 days) — every friction class is a guard

## File layout

Start with `docs/onboarding/README.md` for the AI/developer onboarding path, then see `docs/architecture.md` for the full layout.

## License

MIT
