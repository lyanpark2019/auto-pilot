#!/usr/bin/env bash
# Launch tmux session with N worker panes + 1 monitor pane.
#
# Usage:
#   launch_tmux.sh [N_WORKERS=2] [SESSION=vault-migrate]
#
# Requires tickets already issued via pm.py issue.
set -euo pipefail

N=${1:-2}
SESSION=${2:-vault-migrate}
PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$PLUGIN_ROOT/scripts/migrate"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' exists. Attach with: tmux attach -t $SESSION"
  echo "Or kill first: tmux kill-session -t $SESSION"
  exit 1
fi

# Window 0: monitor
tmux new-session -d -s "$SESSION" -n monitor \
  "while true; do clear; python3 $PY/pm.py status; sleep 5; done"

# Worker panes split from monitor window
for _ in $(seq 1 "$N"); do
  tmux split-window -t "$SESSION":0 -v "python3 $PY/worker.py --poll-interval 3"
  tmux select-layout -t "$SESSION":0 tiled
done

tmux select-pane -t "$SESSION":0.0
echo "Launched session '$SESSION' with $N workers + 1 monitor."
echo "Attach: tmux attach -t $SESSION"
echo "Kill:   tmux kill-session -t $SESSION"
