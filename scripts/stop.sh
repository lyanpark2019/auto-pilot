#!/usr/bin/env bash
set -euo pipefail
PROJECT="$(pwd)"
BASE="$(basename "$PROJECT")"
SESSION="autopilot-$BASE"
CONFIG="$PROJECT/.planning/autopilot/config.json"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  # -s scopes to target session; -a would ignore -t and hit every pane on the server.
  for p in $(tmux list-panes -s -t "$SESSION" -F "#{session_name}:#{window_index}.#{pane_index}"); do
    tmux send-keys -t "$p" C-c 2>/dev/null || true
  done
  sleep 3
  tmux kill-session -t "$SESSION"
  echo "swarm stopped: $SESSION"
else
  echo "no session: $SESSION"
fi

if [ "${1:-}" = "--purge" ]; then
  if [ -f "$CONFIG" ]; then
    for i in $(jq -r '.workers[].id' "$CONFIG"); do
      WT="$PROJECT/../$BASE-worker-$i"
      BR="autopilot/worker-$i"
      [ -d "$WT" ] && git -C "$PROJECT" worktree remove --force "$WT" || true
      git -C "$PROJECT" branch -D "$BR" 2>/dev/null || true
    done
    echo "worktrees purged"
  fi
fi
