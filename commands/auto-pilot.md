---
description: Self-driving development loop. PM (Opus 4.7) + Sonnet 1M workers + dual Codex/Claude adversarial review + phase verify gates. Full auto.
argument-hint: "[start|status|resume|stop] [--spec PATH] [--max-workers N] [--time-box DURATION]"
allowed-tools: Bash, Read, Write, Edit, Agent, Glob, Grep, TaskCreate, TaskList, TaskUpdate
---

# /auto-pilot $ARGUMENTS

Invoke the `auto-pilot` skill. The skill loads `${CLAUDE_PLUGIN_ROOT}/skills/auto-pilot/SKILL.md` and drives the PM-Worker-Reviewer loop.

## Subcommands

- `start` (default) — initialize state, dispatch first phase
- `status` — print `.planning/auto-pilot/state.json` summary
- `resume` — continue from last checkpoint
- `stop` — mark state stopped

## Pre-flight (run before dispatching anything)

1. Confirm repo is git-clean OR `--allow-dirty`
2. Confirm spec exists (newest `docs/specs/*-*.md` OR `--spec` arg OR `SPEC.md`)
3. Confirm `codex` CLI on PATH (for adversarial reviewer)
4. Confirm `.planning/auto-pilot/` exists (create if missing)
5. Print initial scorecard: phase, contracts, est. parallel workers

## Execution

Read `${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py` for the canonical loop. Drive it from the main session — do NOT delegate the PM role to a subagent (Opus 4.7 main session IS the PM).

For each phase:
1. Plan contracts (Read spec + current code)
2. Dispatch workers (1 message, N parallel `Agent` blocks with `subagent_type: "general-purpose"` and the model override `sonnet` — Sonnet 4.6 1M context)
3. Dispatch reviewers (1 message, 2 parallel blocks per worker: codex-adversarial + claude-reviewer)
4. Apply approved fixes, commit atomically, advance state

Stop conditions defined in `SKILL.md`.

## Friction guards (auto-loaded via plugin hooks)

`hooks/preflight-path.sh`, `hooks/pre-edit-composition-root.sh`, `hooks/post-deploy-verify.sh` register via `hooks/hooks.json` and fire automatically.
