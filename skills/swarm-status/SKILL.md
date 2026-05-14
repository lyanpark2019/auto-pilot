---
name: swarm-status
description: Show live status of the autopilot swarm — tmux session, worker queue depth, in-flight tickets, last 5 scores, ledger weights, recent log tail. Use when the user says "swarm status", "/swarm-status", "how is autopilot doing", "show swarm", "ledger".
argument-hint: "[--logs N]"
allowed-tools: Bash, Read
---

# swarm-status

Read-only diagnostics for the swarm in the current project.

## Steps

1. Resolve session name: `session=autopilot-$(basename "$PWD")`.
2. `tmux has-session -t "$session"` → if missing, print "swarm not running" and exit.
3. Run, then format the result as a markdown report:
   ```bash
   ROOT=.planning/autopilot
   tmux list-panes -t "$session" -a -F "#{window_index}.#{pane_index} #{pane_current_command}"
   echo "queues:"
   for i in $(jq -r '.workers[].id' "$ROOT/config.json"); do
     echo "  worker-$i inbox=$(ls "$ROOT"/inbox/worker-$i 2>/dev/null | wc -l)"
   done
   echo "in_progress=$(ls "$ROOT"/in_progress 2>/dev/null | wc -l)"
   echo "done=$(ls "$ROOT"/done 2>/dev/null | wc -l)"
   echo "scores=$(ls "$ROOT"/scores/*.json 2>/dev/null | wc -l)"
   echo "ledger:"
   jq '.workers' "$ROOT/ledger/agent-scores.json" 2>/dev/null
   echo "recent scores:"
   ls -t "$ROOT"/scores/*.json 2>/dev/null | head -5 | while read f; do
     jq -c '{id:.ticket_id,worker,total,verdict}' "$f"
   done
   echo "pm log tail:"
   tail -${LOGS:-15} "$ROOT/logs/pm.log" 2>/dev/null
   ```
4. Render as a readable report. Highlight any worker with `weight < 0.7` (struggling) or `weight > 1.3` (top performer).

## Notes for Claude

- Read-only. Do not write. Do not modify the ledger.
- If `--logs N` arg given, show last N lines of pm.log.
- Surface in-flight tickets older than 30 minutes as warnings (possibly stuck).
