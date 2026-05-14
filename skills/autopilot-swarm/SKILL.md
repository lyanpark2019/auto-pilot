---
name: autopilot-swarm
description: Launch the autopilot multi-agent swarm in the current project. Boots a tmux session inside the current terminal with 1 PM (claude opus 4.7) plus 4-10 configurable workers (claude/codex). Use when the user says "start autopilot", "launch swarm", "run autopilot-swarm", "/autopilot-swarm", "deploy multi-agent system", or similar.
argument-hint: "[--workers N] [--config <path>]"
allowed-tools: Bash, Read, Write
---

# autopilot-swarm — launch

This skill bootstraps the autonomous multi-agent swarm in the **current working
directory** (whichever project the user is in). Universal: works for any
language/framework — `swarm-explorer` agent maps the project at bootstrap.

## Steps

1. **Check for existing config** at `.planning/autopilot/config.json`.
   - If missing, **invoke `swarm-init` skill first** to create one. Do not
     proceed without config.
2. **Verify dependencies** with Bash:
   ```bash
   for cmd in tmux jq envsubst claude codex git; do
     command -v "$cmd" >/dev/null || { echo "missing: $cmd"; exit 1; }
   done
   ```
3. **Run the launcher**:
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/start.sh"
   ```
   `start.sh`:
   - Reads `.planning/autopilot/config.json` (worker count, models, initial goal)
   - Creates `<project>/.planning/autopilot/` bus directories
   - Creates N git worktrees at `<project>/../<basename>-worker-{1..N}` on
     branches `autopilot/worker-{1..N}`
   - Starts tmux session `autopilot-<basename>` with 1 PM pane + N worker panes
     (split across 1-2 windows depending on N)
   - Sends pane commands: `bash run-pm.sh` and `bash run-worker.sh <N> <model>`
   - `exec tmux attach` in the **current terminal** (no new window)

## Arguments

- `--workers N` — override config worker count (4-10, default from config)
- `--config <path>` — alternate config json (default `.planning/autopilot/config.json`)

## Notes for Claude

- This skill must NOT prompt the user mid-launch. Either config exists and we
  go, or we redirect to `swarm-init` and stop.
- Resume semantics: if tmux session already exists, just attach.
- Print one final line: `swarm online: <session-name>, <N> workers`.
