#!/usr/bin/env bash
set -euo pipefail
PROJECT="$(pwd)"
BASE="$(basename "$PROJECT")"
SESSION="autopilot-$BASE"
CONFIG="$PROJECT/.planning/autopilot/config.json"

_stop_cleanup() {
  local lockdir="$PROJECT/.planning/autopilot/ledger/dispatch.lock.d"
  if [ -d "$lockdir" ]; then
    local lockholder_pid_file="$lockdir/lockholder.pid"
    if [ ! -f "$lockholder_pid_file" ] || ! kill -0 "$(cat "$lockholder_pid_file")" 2>/dev/null; then
      rm -rf "$lockdir" || true
    fi
  fi
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  echo "cleanup done" >&2
}

# Guarantee lockdir + tmux cleanup even when stop.sh is interrupted mid-loop.
trap '_stop_cleanup' EXIT INT TERM

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
