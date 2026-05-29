#!/usr/bin/env bash
# tmux-launcher.sh — optional visible-pane launcher for codebase-perfection-loop
#
# Use only when the user explicitly wants to *watch* the 10 workers run.
# Default mode (Agent run_in_background) is faster + structured. This is purely
# for visibility (live tail per pane).
#
# Usage:
#   tmux-launcher.sh <session-name> <prompts-dir>
#
# prompts-dir must contain w1.txt … w10.txt — one self-contained worker prompt each.
# Output goes to <prompts-dir>/logs/w<N>.log per worker.
#
# Models:
#   W1, W2, W5, W8 → claude (Sonnet 4.6) via `claude -p`
#   W3, W6, W10    → claude (Plan agent shape, Sonnet 4.6 underlying)
#   W4, W7         → codex with model gpt-5.5-high
#   W9             → claude (general-purpose shape)
#
# Requirements: tmux, claude CLI, codex CLI

set -euo pipefail

SESSION="${1:-cpl-audit}"
PROMPTS_DIR="${2:?prompts-dir required}"

if [ ! -d "$PROMPTS_DIR" ]; then
  echo "prompts dir not found: $PROMPTS_DIR" >&2
  exit 1
fi
mkdir -p "$PROMPTS_DIR/logs"

# helper — kebab name → CLI command
cmd_for_worker() {
  local n="$1"
  local prompt_file="$PROMPTS_DIR/w${n}.txt"
  local log_file="$PROMPTS_DIR/logs/w${n}.log"
  case "$n" in
    1|2|3|5|6|8|9|10)
      echo "claude -p \"\$(cat '$prompt_file')\" 2>&1 | tee '$log_file'"
      ;;
    4|7)
      echo "codex exec --model gpt-5.5-high \"\$(cat '$prompt_file')\" 2>&1 | tee '$log_file'"
      ;;
    *)
      echo "echo unknown worker $n"
      ;;
  esac
}

# start tmux session
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "session $SESSION already exists — kill it first" >&2
  exit 1
fi

tmux new-session -d -s "$SESSION" -n "pm" "echo 'PM pane — synthesis lives here'; bash"

# spawn 10 panes (in 2 columns of 5 each is readable on most monitors)
for n in 1 2 3 4 5 6 7 8 9 10; do
  cmd=$(cmd_for_worker "$n")
  tmux new-window -t "$SESSION" -n "w$n" "$cmd"
done

# select pm
tmux select-window -t "$SESSION:pm"

echo "session $SESSION launched. Attach with:"
echo "  tmux attach -t $SESSION"
echo ""
echo "Per-worker logs: $PROMPTS_DIR/logs/w*.log"
echo "When all w*.log files have a final summary line, run the synthesis step."
