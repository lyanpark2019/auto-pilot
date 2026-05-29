#!/usr/bin/env bash
# spawn-tmux.sh — Boot a tmux session with N+1 panes for harness multi-worker.
#
# Layout: tiled grid. pane 0 = PM (Opus attaches here); pane 1..N = Codex worker
# polling loops (worker-loop.sh).
#
# Usage:
#   bash spawn-tmux.sh <project_root> [N=5] [SESSION=harness]
#
# Attach: tmux attach -t <SESSION>
# Teardown: tmux kill-session -t <SESSION>

set -euo pipefail

PROJECT_ROOT="${1:?project_root required}"
N_WORKERS="${2:-5}"
SESSION="${3:-harness}"

PLANNING_DIR="${PROJECT_ROOT}/.planning/harness-rewrite"
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKER_LOOP="${SKILL_ROOT}/scripts/worker-loop.sh"

[[ -x "$WORKER_LOOP" ]] || { echo "ERROR: ${WORKER_LOOP} not executable" >&2; exit 1; }
[[ -d "$PLANNING_DIR" ]] || { echo "ERROR: ${PLANNING_DIR} missing — run codex-analyze.sh init first" >&2; exit 1; }

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '${SESSION}' exists. Attach: tmux attach -t ${SESSION}"
  exit 0
fi

# Pane 0 = PM.
tmux new-session -d -s "$SESSION" -n auto -c "$PROJECT_ROOT"
tmux send-keys -t "${SESSION}:auto.0" \
  "echo '[pane 0] PM (attach Claude Code here). Outbox tail: tail -f ${PLANNING_DIR}/outbox/worker-*/*.md'" C-m

# Add N more panes (1 PM + N workers = N+1 total).
for ((i=1; i<=N_WORKERS; i++)); do
  tmux split-window -t "${SESSION}:auto" -h -c "$PROJECT_ROOT"
  tmux select-layout -t "${SESSION}:auto" tiled
done

# Start worker-loop.sh in panes 1..N (pane 0 stays as PM).
# Pane indexing after tiled: 0 still PM, 1..N are workers.
for ((N=1; N<=N_WORKERS; N++)); do
  tmux send-keys -t "${SESSION}:auto.${N}" \
    "WORKER_ID=${N} PLANNING_DIR='${PLANNING_DIR}' bash '${WORKER_LOOP}'" C-m
done

echo "tmux '${SESSION}' ready: 1 PM pane + ${N_WORKERS} worker pane"
echo "Attach: tmux attach -t ${SESSION}"
echo "Drop tickets into: ${PLANNING_DIR}/inbox/worker-{1..${N_WORKERS}}/*.json"
