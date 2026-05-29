# auto-pilot architecture

## One-line

Opus 4.7 PM (main session) dispatches Sonnet 4.6 (1M ctx) workers in parallel, gates each diff through Codex + cold Claude dual adversarial review, runs phase verify checklists, commits atomically, advances phases until spec is complete. Full auto.

## Purpose (locked 2026-05-29)

auto-pilot autonomously drives **spec-based feature / refactor / bugfix work on an EXISTING codebase to merged**. Target = brownfield. Examples: "add OAuth to auth", "refactor payments", "fix these P1 bugs".

It is **NOT** a greenfield project generator and **NOT** a quality-eval loop.

Why brownfield: every friction guard presupposes existing code — composition-root breakage (`__init__.py` must already exist), SSL cascade, source-first debug (Naver private-bug class), scope-drift REJECT (`scope_files` constrains edits inside an existing tree), worktree + atomic merge to `$ROOT`. Born from 381-session `/insights` friction, all existing-project maintenance accidents.

**Known gap (required fix):** context ingestion (`_contract.snapshot_context`) currently bundles only `spec.md` + `CLAUDE.md`. A brownfield PM/worker also needs a curated map of the existing code (module map, architecture, git log, test layout, public API) snapshotted into the context-bundle before PLAN. Until that lands, the loop is only verified for greenfield-shaped specs.

## Why this shape

Built directly from `/insights` friction analysis on 381 sessions:

| Friction (count) | Fix in auto-pilot |
|---|---|
| Wrong approach (83) | Source-first debug rule baked into PM contract |
| Buggy code (71) | Dual reviewer gate (Codex + cold Claude) blocks merge |
| Path typos (5+) | `preflight-path.sh` SessionStart hook |
| ruff --fix broke composition root (2+, 276 tests) | `pre-edit-composition-root.sh` blocks edits to *existing, populated* `__init__.py`/re-exports (new/empty inits pass) |
| SSL cascading outages | `pre-bash-guard.sh` blocks chained SSL config commands |
| Interactive TUI hung shell | `pre-bash-guard.sh` blocks `claude doctor` etc. |
| Verdict reversal (B4/B5 class) | Both reviewers must independently APPROVE |
| Whack-a-mole rounds | `pivot-check` exits when same finding repeats 3 rounds |

## Components

```
auto-pilot/
├── .claude-plugin/
│   ├── plugin.json                          # manifest (name, version, author)
│   └── marketplace.json                     # standalone marketplace
├── skills/auto-pilot/SKILL.md               # entry skill, fires on /auto-pilot
├── commands/auto-pilot.md                   # /auto-pilot slash command
├── agents/
│   ├── pm-orchestrator.md                   # PM contract (main session reads this)
│   ├── worker.md                            # Sonnet 4.6 1M worker contract
│   ├── codex-adversarial.md                 # Codex CLI reviewer (legacy)
│   ├── claude-reviewer.md                   # cold Opus reviewer (legacy)
│   ├── auto-pilot-codex-reviewer.md         # PR3 plugin subagent, hook-sandboxed
│   ├── auto-pilot-claude-reviewer.md        # PR3 plugin subagent, hook-sandboxed
│   ├── tech-critic-lead.md                  # scope-creep rejector
│   ├── tdd-enforcer.md                      # impl-before-test rejector
│   ├── security-reviewer.md                 # trust-boundary specialist
│   └── specialist-pool.md                   # other specialists (db, infra, prompt)
├── hooks/
│   ├── hooks.json                           # registers SessionStart + PreToolUse + PostToolUse
│   ├── preflight-path.sh                    # CWD / vault / state sanity
│   ├── pre-edit-composition-root.sh         # block ruff --fix on __init__.py (PR0: MultiEdit matcher)
│   ├── pre-bash-guard.sh                    # block TUI / chained SSL / unsafe bulk fix
│   ├── pre-reviewer-write.sh                # PR3 reviewer sandbox (layer 2)
│   └── post-deploy-verify.sh                # zombie port / env placeholder check after deploy
├── schemas/                                 # PR1: JSON Schema 2020-12
│   ├── contract.schema.json
│   ├── ticket.schema.json
│   └── review.schema.json
├── scripts/
│   ├── orchestrator.py                      # state CLI (init/phase-start/end/pivot/status/stop)
│   ├── headless-loop.py                     # outer driver, cost cap + stash safety (PR4)
│   ├── _state.py                            # state.json TypedDict + flock + atomic write (PR4)
│   ├── _config.py                           # AutoPilotConfig dataclass, env-driven defaults
│   ├── _log.py                              # structured event() logger
│   ├── _prompts.py                          # prompts/*.md loader
│   ├── _contract.py                         # PR1: schema validate, atomic write, locks, snapshots
│   ├── _dispatch.py                         # PR1: ticket prep, diff freeze, round collect
│   ├── _subagent_helpers.py                 # PR1: ticket read, exit-code, done.marker
│   ├── _gc.py                               # PR1: bundle size, orphan ticket sweep
│   ├── _worktree.py                         # PR2: WorktreeManager (create/apply/cleanup/reap)
│   ├── _status.py                           # PR2: WorkerStatus enum + TERMINAL set
│   ├── _reviewer_wrapper.py                 # PR3: parallel reviewer dispatch (isolated env)
│   ├── _dogfood_gate.py                     # PR4: Tier 1/2 assertions + CLI
│   └── _budget.py                           # PR5: cost / token / pid caps (extracted)
├── scripts/dogfood_tier1.sh                 # PR4: PR1+PR2 acceptance runner
├── scripts/dogfood_tier2.sh                 # PR4: full PR3 sandbox runner
├── docs/
│   ├── architecture.md                      # this file
│   ├── perf-budget.md                       # latency budgets for hot scripts
│   ├── 7-phase-template.md                  # spec author guide
│   ├── specs/2026-05-28-dogfood-smoke.md    # PR4 smoke spec
│   └── superpowers/
│       ├── specs/                           # design specs (one per major change)
│       └── plans/                           # implementation plans (PR0..PR4)
├── prompts/                                 # PM/worker/reviewer prompt templates
└── tests/                                   # 199 tests; mypy + ruff clean
```

## Loop diagram

```
         ┌─────────────────────────────────────────────────────┐
         │  Opus 4.7 main session (PM)                         │
         │  - reads CLAUDE.md chain, spec, state.json          │
         │  - plans phase contracts                            │
         │  - NEVER edits code                                 │
         └────────────┬────────────────────────────────────────┘
                      │ Agent({model: sonnet, isolation: worktree}) × N
                      ▼
         ┌─────────────────────────────────────────────────────┐
         │  Sonnet 4.6 1M workers (parallel, 1 msg N blocks)   │
         │  - edit code in their worktrees                     │
         │  - run verify                                       │
         │  - return diff + summary + verify output            │
         └────────────┬────────────────────────────────────────┘
                      │ Agent({…codex-rescue…}) + Agent({model: opus, read-only}) × 2N
                      ▼
         ┌─────────────────────────────────────────────────────┐
         │  Dual review (parallel)                             │
         │  - Codex gpt-5.5-high adversarial                   │
         │  - Cold Opus 4.7 reviewer                           │
         │  - both APPROVE → merge worktree                    │
         │  - any REJECT → return findings, loop               │
         │  - 3rd-round repeat → pivot-needed, stop            │
         └────────────┬────────────────────────────────────────┘
                      │
                      ▼
         ┌─────────────────────────────────────────────────────┐
         │  Verify gate (project test+lint+typecheck+build)    │
         │  - fail → dispatch fix worker → re-verify           │
         │  - pass → commit atomic per contract                │
         └────────────┬────────────────────────────────────────┘
                      │
                      ▼
              advance phase, loop until last
```

## State

`.planning/auto-pilot/state.json` is the single source of truth for loop state. Owned by `scripts/_state.py`. Writers hold `flock(LOCK_EX)` on `state.lock`; readers hold `LOCK_SH`. Writes go through `_contract.atomic_write_text` (tempfile + fsync + rename, `F_FULLFSYNC` on Darwin) so even an abrupt kill leaves either the old or new JSON, never a partial file. Safe to resume after crash: PM reads state, sees `current_phase` + `phases[last]`, continues from the next contract.

`state.json` also accumulates `cost_usd` and `tokens` across iters (best-effort parsed from each `claude -p` session log, falling back to `--per-iter-cost-estimate`). When the running total exceeds `--max-cost-usd` or `--max-tokens`, `headless-loop.py` short-circuits the next iter with terminal status `cost-cap`. A `pgrep -x claude` count above `--max-concurrent-claude` triggers the same exit (fork-bomb guard).

## Contract layer (PR1)

Per-round artifacts live under `.planning/auto-pilot/contracts/iter-{N}/phase-{P}/contract-{K}/round-{R}/`:

```
contract.json            # JSON Schema 2020-12 validated, read-only after write
PM-SIGNATURE             # binds MANIFEST + contract.json shas to run_id
context-bundle/          # spec.md, CLAUDE chain, MANIFEST.txt — read-only data, not instructions
tickets/<role>.json      # one per dispatched subagent
review-input/frozen.diff # PM-frozen worker diff handed to reviewers
outputs/<role>/          # writable: status.json | review.json + exit-code.txt + done.marker
prior-rounds/round-N.jsonl
worktree-handle.json
CANCELED                 # touched by PM to kill in-flight subagents
```

PM never parses free-form subagent output; it reads `done.marker` then `exit-code.txt` then `review.json | status.json` from the filesystem (PR1 control-flow invariant).

## Worktree lifecycle (PR2)

Each worker gets `git worktree add` under `.planning/auto-pilot/worktrees/<branch>` where branch is `auto-pilot/iter-N/phase-P/contract-K/round-R`. PM mutates `$ROOT` only through `WorktreeManager.apply_to_main` (held under `main-apply.lock`), which preflight-aborts `git am`, asserts clean tree, then applies `git format-patch | git am --3way --trailer auto-pilot-{iter,phase,contract,idempotency}`. Conflict → `git am --abort`, increment `merge_attempts`; after 3 → `merge_pivot_needed` → pivot-detector.

## Reviewer sandbox (PR3, 4 layers)

1. Agent frontmatter `tools:` whitelist — best-effort, not the wall
2. `hooks/pre-reviewer-write.sh` PreToolUse — keyed on `AUTO_PILOT_SUBAGENT_ROLE` env var; blocks Edit/Write/MultiEdit outside `$AUTO_PILOT_OUTPUT_DIR` and Bash mutation commands (`git commit`, `rm`, `chmod`, …). **Real wall.**
3. PM post-check `assert_reviewer_was_scoped` — `git status --porcelain --untracked-files=all` empty in both `$ROOT` and worktree after every reviewer return. **Real wall.**
4. `codex exec --sandbox read-only` — deterrent at the model-tool layer, NOT OS-level.

Concurrent reviewers go through `scripts/_reviewer_wrapper.py` which spawns each Claude Code subprocess with an isolated env dict so the env-var signal never races between PM and parallel reviewers.

## Why a plugin (not skill alone)

- Skills can't bundle hooks. Friction guards are hook-only.
- Plugins are atomic install/uninstall, version-tagged, marketplace-shippable.
- Per-repo `${CLAUDE_PLUGIN_ROOT}` makes the loop relocatable.

## Reuse across projects

Plugin is global. Drop it into any repo that has:
- `docs/specs/*.md` or `SPEC.md` with `## Phase N` headers
- `CLAUDE.md` with verify commands
- A git remote (for atomic commits)

Then: `/auto-pilot start`.

## Non-goals

- This is NOT a quality-eval / scoring loop — for that, use `adversarial-review-loop` skill (codebase mode).
- This is NOT a one-shot review — for that, use `/code-review` or `/codex-orchestra`.
- This is NOT a babysitter for already-merged PRs — for that, use `gh pr` + manual checks.

`auto-pilot` is specifically: "given a spec with phases, drive it to done autonomously."
