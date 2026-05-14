---
name: swarm-stop
description: Stop the autopilot swarm tmux session and optionally remove worker worktrees + branches. Use when the user says "stop swarm", "kill autopilot", "/swarm-stop", "shutdown autopilot", "tear down swarm".
argument-hint: "[--purge]"
allowed-tools: Bash
---

# swarm-stop

Graceful shutdown of the swarm in the current project.

## Steps

1. `bash "${CLAUDE_PLUGIN_ROOT}/scripts/stop.sh" $ARGUMENTS`

`stop.sh` behaviour:
- Resolves `session=autopilot-$(basename "$PWD")`.
- If `tmux has-session`, sends `C-c` to all panes (graceful), waits 3s, then `tmux kill-session`.
- If `--purge`, runs `git worktree remove --force` on each worker tree and deletes the `autopilot/worker-N` branches.
- Never touches `main` or non-autopilot branches.
- Leaves `.planning/autopilot/` intact (logs/scores preserved unless user manually rm).

Print: `swarm stopped: <session>` (and `worktrees purged` if `--purge`).

## Notes for Claude

- Always confirm `--purge` with the user once before passing it through.
  (Worktrees may contain uncommitted work.)
