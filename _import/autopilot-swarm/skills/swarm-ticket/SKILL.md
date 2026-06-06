---
name: swarm-ticket
description: Manually inject a ticket into a worker's inbox without waiting for PM dispatch. Use when the user says "give swarm a task", "swarm-ticket", "/swarm-ticket", "inject ticket", "TODO into swarm".
argument-hint: "<worker-id> <task description> [--scope <path>]+ [--accept <check>]+"
allowed-tools: Bash, Write
---

# swarm-ticket — manual injection

Bypass PM dispatch and put a ticket directly into `worker-N` inbox.

## Parse

`$ARGUMENTS` form: `<worker-id> <task...> [--scope p1] [--scope p2] [--accept c1] [--accept c2]`

- `worker-id` ∈ `1..N` per `config.json`
- `task` is everything else up to first `--scope` / `--accept`
- repeat `--scope` / `--accept` for multiple

If user omits `--scope`, default to `["."]` (full repo, lower priority for PM dispatch overlap).
If user omits `--accept`, derive 1 sane check from project type via `swarm-explorer` snapshot
(`.planning/autopilot/knowledge/project-snapshot.md`).

## Output

Write `<cwd>/.planning/autopilot/inbox/worker-<id>/T-manual-<epoch>.json`:

```json
{
  "id": "T-manual-<epoch>",
  "title": "<<task summary>>",
  "prompt": "<<full task as user typed it, plus scope reminder>>",
  "scope_paths": ["..."],
  "acceptance": ["..."],
  "issued_at": "<iso8601>",
  "issued_by": "user",
  "worktree": "../<basename>-worker-<id>"
}
```

## Steps

1. Validate `worker-id` exists in `config.json`.
2. Verify swarm is running (`tmux has-session`). If not, suggest `/autopilot-swarm:autopilot-swarm`.
3. Write atomically. Print confirmation: `injected T-manual-<epoch> → worker-<id> (will claim within 8s)`.

## Notes for Claude

- Do NOT run the task directly — only deposit the ticket.
- One invocation = one ticket.
