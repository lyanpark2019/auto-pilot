---
name: auto-pilot-server
description: Launch the headless infinite auto-pilot loop. Forks a Python driver that spawns `claude -p --dangerously-skip-permissions` sessions per phase, with pre-phase HEAD snapshot + non-destructive stash on failure. Truly hands-free.
argument-hint: "[--max-iter N] [--sleep SEC] [--once] [--timeout-build SEC]"
allowed-tools: Bash, Read
---

# /auto-pilot-server $ARGUMENTS

Launch the headless infinite loop driver. This is `/auto-pilot start` taken to its logical conclusion: a Python process running outside the conversation, spawning fresh `claude -p` sessions for each phase iteration. The conversation that invoked `/auto-pilot-server` is NOT the loop — it just kicks off the driver and exits.

## Pre-flight

1. Confirm `.planning/auto-pilot/state.json` exists (run `/auto-pilot start` once first to initialize)
2. Confirm `claude` CLI on PATH (`which claude`)
3. Confirm git is clean OR `--allow-dirty`
4. Confirm `codex` CLI on PATH (the headless sessions will need it for adversarial review)

## Launch

The user should run the driver in their own terminal so it survives Claude Code session restarts:

```bash
cd /path/to/repo
python ${CLAUDE_PLUGIN_ROOT}/scripts/headless-loop.py \
  --max-iter 100 \
  --sleep 10 \
  --timeout-build 14400
```

For a smoke test (one iteration, no infinite loop):

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/headless-loop.py --once
```

If running through this slash command, dispatch via Bash with `run_in_background: true`:

```
Bash({
  command: "cd $(pwd) && python ${CLAUDE_PLUGIN_ROOT}/scripts/headless-loop.py --max-iter 100 --sleep 10 > .planning/auto-pilot/server.log 2>&1",
  run_in_background: true,
  description: "Launch auto-pilot headless loop driver"
})
```

Then tail logs:

```
tail -f .planning/auto-pilot/server.log
```

## How each iteration works

For iteration N at phase P:

1. Driver snapshots current HEAD
2. Driver spawns `claude -p --dangerously-skip-permissions "<HEADLESS_PREAMBLE> resume auto-pilot iter N phase P ..."` with `HARNESS_HEADLESS=1`
3. Claude session runs the `auto-pilot` skill — plans contracts, dispatches workers + reviewers (tech-critic-lead BEFORE workers; codex/claude/review-gatekeeper modes/specialists AFTER), commits with `auto-pilot-iter: N` trailer, advances phase
4. Session exits naturally
5. Driver reads state.json
   - `status=success` (final phase done) → driver exits 0
   - `status=stopped` (user `/auto-pilot stop`) → driver exits 0
   - `status=pivot-needed` (3rd-round same finding) → driver exits 1
   - `status=failed` → driver stashes any dirty root changes with a recoverable `auto-pilot-iter-N-failed` label, exits 1
   - `status=running` → driver sleeps `--sleep` seconds, next iteration
6. Driver caps at `--max-iter` total iterations

## Stop conditions (driver-side)

- Terminal status in state.json → exit
- `--max-iter` reached → exit
- SIGTERM/SIGINT → driver exits, in-flight session is killed

## Log locations

- Driver output: `.planning/auto-pilot/server.log`
- Per-iteration session output: `.planning/auto-pilot/logs/iter-NNNN-phase-P.log`
- State checkpoint: `.planning/auto-pilot/state.json`

## When NOT to use /auto-pilot-server

- You want to watch each phase yourself → use `/auto-pilot start` instead (runs in current conversation)
- Repo has no spec with phases → server will loop forever doing nothing; use `/auto-pilot start` first to validate
- You're on flaky power / unsaved laptop work → driver is robust to crashes (resumable from state.json), but a partial commit is still a partial commit. Use `--allow-dirty` consciously.
