# auto-pilot swarm — docs

The swarm backend (`swarm/`) is an **optional parallel execution model**: a
tmux-multiplexed PM + N worker agents that run concurrently on a project.
It is a separate execution path from the core auto-pilot loop
(`scripts/orchestrator.py` + `scripts/headless-loop.py`).

## Do not run concurrently with the core loop

The core loop writes state to `.planning/auto-pilot/state.json` (with hyphen).
The swarm writes to `.planning/autopilot/` (no hyphen). While the paths are
distinct, both drive agentic mutations on the same repository and can cause
conflicting git commits or schema-state races.

`swarm/scripts/start.sh` enforces this: if `.planning/auto-pilot/state.json`
exists and its `status` field equals `"running"`, start.sh exits 3 with:

```
swarm: refusing to start — core auto-pilot loop is running (state.json status=running)
```

Absent state file or any terminal status (`stopped`, `failed`, `success`,
`pivot-needed`) does not block the swarm.

To start the swarm after a core-loop run, ensure the loop has reached a
terminal state (check with `python3 scripts/orchestrator.py status`), then
run `bash swarm/scripts/start.sh`.

## Architecture docs

- `docs/architecture/merge-lock.md` — merge-lock protocol
- `docs/architecture/tmux-kill-switch.md` — STOP sentinel + tmux kill-switch
