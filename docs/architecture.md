# auto-pilot architecture

## One-line

Opus 4.7 PM (main session) dispatches Sonnet 4.6 (1M ctx) workers in parallel, gates each diff through Codex + cold Claude dual adversarial review, runs phase verify checklists, commits atomically, advances phases until spec is complete. Full auto.

## Why this shape

Built directly from `/insights` friction analysis on 381 sessions:

| Friction (count) | Fix in auto-pilot |
|---|---|
| Wrong approach (83) | Source-first debug rule baked into PM contract |
| Buggy code (71) | Dual reviewer gate (Codex + cold Claude) blocks merge |
| Path typos (5+) | `preflight-path.sh` SessionStart hook |
| ruff --fix broke composition root (2+, 276 tests) | `pre-edit-composition-root.sh` blocks edits to `__init__.py`/re-exports |
| SSL cascading outages | `pre-bash-guard.sh` blocks chained SSL config commands |
| Interactive TUI hung shell | `pre-bash-guard.sh` blocks `claude doctor` etc. |
| Verdict reversal (B4/B5 class) | Both reviewers must independently APPROVE |
| Whack-a-mole rounds | `pivot-check` exits when same finding repeats 3 rounds |

## Components

```
auto-pilot/
├── .claude-plugin/
│   ├── plugin.json              # manifest (name, version, author)
│   └── marketplace.json         # standalone marketplace
├── skills/auto-pilot/SKILL.md   # entry skill, fires on /auto-pilot
├── commands/auto-pilot.md       # /auto-pilot slash command
├── agents/
│   ├── pm-orchestrator.md       # PM contract (main session reads this)
│   ├── worker.md                # Sonnet 4.6 1M worker contract
│   ├── codex-adversarial.md     # Codex CLI reviewer
│   └── claude-reviewer.md       # cold Opus reviewer
├── hooks/
│   ├── hooks.json               # registers SessionStart + PreToolUse + PostToolUse
│   ├── preflight-path.sh        # CWD / vault / state sanity
│   ├── pre-edit-composition-root.sh   # block ruff --fix on __init__.py
│   ├── pre-bash-guard.sh        # block TUI / chained SSL / unsafe bulk fix
│   └── post-deploy-verify.sh    # zombie port / env placeholder check after deploy
├── scripts/
│   └── orchestrator.py          # state mgmt helper (PM calls this)
└── docs/architecture.md         # this file
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

`.planning/auto-pilot/state.json` is the single source of truth for loop state. Owned by `scripts/orchestrator.py`. Safe to resume after crash: PM reads state, sees `current_phase` + `phases[last]`, continues from the next contract.

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
