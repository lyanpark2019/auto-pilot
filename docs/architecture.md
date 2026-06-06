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

## Components (merged unified-coding-system layout, 2026-06)

```
auto-pilot/
├── .claude-plugin/
│   ├── plugin.json                          # manifest (name, version, author)
│   └── marketplace.json                     # standalone marketplace
├── .mcp.json                                # bundled MCP server config (notebooklm vault)
├── skills/                                  # 19 dirs / 18 active SKILL.md
│   ├── auto-pilot/                          # entry skill, fires on /auto-pilot (core loop)
│   ├── adversarial-review-loop/             # dual-track review: branch / codebase / multi-agent modes
│   ├── quality-eval/                        # 13-dim rubric SoT
│   ├── pm-quality-harness-loop/             # superset quality-lift + ship orchestrator
│   ├── residue-audit/                       # semantic dead-code / duplicate audit
│   ├── doc-management/                      # docs flagship: REBUILD / MAINTAIN / AUDIT (+ L2/L3 guard scripts)
│   ├── setup-harness/                       # harness bootstrap (+ scripts/ references/ templates/ evals/)
│   ├── sha-deploy-standard/                 # SHA-pinned deploy standard
│   ├── codex-orchestra/                     # conductor: Claude plans/reviews, Codex implements
│   ├── swarm/ (init/start/status/stop/ticket) + swarm-bench/   # parallel execution backend skills
│   ├── improve-codebase-architecture/, diagnosing-{llm-output-leaks,stale-runtime}/
│   └── codebase-perfection-loop/            # DEPRECATED shell — references/ kept (rubric provenance)
├── commands/                                # 16 slash commands: auto-pilot{,-server}, eval-run,
│                                            #   harness (plan/build/qa), harness-ops (setup/drift/loop/score/verify),
│                                            #   vault-{build,score,dashboard,selftest},
│                                            #   setup-claude-md, sha-deploy-init
│                                            # (harness 8→2; vault 10→4; quality-loop+nbm-to-obsidian+goal-* removed)
├── agents/                                  # 23 agent contracts (review substance: skills/adversarial-review-loop/references/)
│   ├── core loop: pm-orchestrator, worker, retro
│   ├── review: codex-adversarial + claude-reviewer (legacy),
│   │   auto-pilot-{codex,claude}-reviewer (PR3, hook-sandboxed), tech-critic-lead,
│   │   tdd-enforcer, security-reviewer, specialist-pool, code-perfector
│   ├── harness trio: harness-{planner,generator,evaluator}
│   ├── swarm: swarm-{explorer,monitor,verifier}
│   └── vault set: vault-pm-orchestrator + vault-{edge-curator,graph-enricher,knowledge-author,structure-curator}
│       (4 merged agents, 2026-06 round-2 — 25 legacy vault workers removed; repo-docs fixing → doc-management)
│   (goal-{scout,judge,worker} removed from plugin — live in global ~/.claude/agents/)
├── hooks/
│   ├── hooks.json                           # SessionStart + PreToolUse + PostToolUse registrations
│   ├── preflight-path.sh                    # CWD / vault / state sanity
│   ├── pre-edit-composition-root.sh         # block ruff --fix on __init__.py (PR0: MultiEdit matcher)
│   ├── pre-bash-guard.sh                    # block TUI / chained SSL / unsafe bulk fix
│   ├── pre-reviewer-write.sh                # PR3 reviewer sandbox (layer 2)
│   ├── post-deploy-verify.sh                # zombie port / env placeholder check after deploy
│   ├── doc-sync-update.sh                   # merged graph-freshness watcher: code graph stale-flag + vault raw/sources .md eager graphify update (feeds doc-management MAINTAIN)
│   ├── notebooklm_delete_gate.sh            # confirm-gated notebooklm deletes (Bash CLI + MCP shapes)
│   ├── pm_final_report.sh                   # PM final-report emission
│   ├── guard-destructive.py, codex-conductor-guard.py   # destructive-command + conductor guards
│   └── test_{guard_destructive,codex_conductor_guard,notebooklm_delete_gate}.py  # hook self-tests
├── schemas/                                 # PR1: contract/ticket/review JSON Schema 2020-12
│                                            #   (swarm's ticket/score/verify/plugin schemas → swarm/schemas/)
├── scripts/                                 # orchestrator.py, headless-loop.py, PR1-PR5 _*.py helpers
│                                            #   (_state/_config/_log/_prompts/_contract/_dispatch/
│                                            #   _subagent_helpers/_gc/_worktree/_status/_reviewer_wrapper/
│                                            #   _dogfood_gate/_budget), build_dashboard_data.py,
│                                            #   dogfood_tier{1,2}.sh, quality/ (module-size gate)
├── prompts/                                 # PM/worker/reviewer prompt templates
├── vault/                                   # export layer (vault-builder absorbed wholesale):
│                                            #   pipeline/ sources/ scripts/ rubrics/ templates/
│                                            #   dashboard/ tests/ (62 pytest)
├── swarm/                                   # parallel execution backend: scripts/ schemas/ tests/ docs/
├── codex/                                   # 12 codex skill forks (repo = SoT) + sync-to-codex.sh
├── deploy/                                  # sha-deploy templates
├── dashboard/                               # plugin structure + scorecard dashboard (index.html, data.js)
├── evals/                                   # eval harness: cases/, _fixtures/, baseline.json
├── docs/
│   ├── architecture.md                      # this file
│   ├── master-plan.md                       # purpose, skill-integration map, roadmap
│   ├── perf-budget.md                       # latency budgets for hot scripts
│   ├── 7-phase-template.md                  # spec author guide
│   ├── specs/                               # PR-input specs (incl. 2026-06-06 unified-coding-system)
│   └── superpowers/{specs,plans}/           # design specs + implementation plans
└── tests/                                   # 228 tests (pytest); mypy + ruff clean
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
