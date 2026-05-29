#!/usr/bin/env bash
# UserPromptSubmit OR SessionStart: inject .claude/STEER.md content into the agent's context
# so an operator can steer the autonomous loop between iterations without restarting.
# Pattern from anthropics/cwc-long-running-agents.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
STEER="$ROOT/.claude/STEER.md"

[ -f "$STEER" ] || exit 0
[ -s "$STEER" ] || exit 0

content=$(cat "$STEER")
jq -Rn --arg msg "=== Operator steering note ===\n$content" \
  '{hookSpecificOutput:{hookEventName:"UserPromptSubmit",additionalContext:$msg}}'

# Optional: clear STEER.md after consuming so it's one-shot
# rm "$STEER"

exit 0
