#!/usr/bin/env bash
# PreToolUse hook: enforce daily/session token-cost budget.
#
# Two budget sources:
#   1. .claude/harness/budget.json — multi-agent harness budget (max_usd, spent_usd)
#   2. HARNESS_DAILY_BUDGET_USD env var — hard daily cap
#
# Cheap implementation: tracks spend locally based on PostToolUse usage data.
# For authoritative Anthropic billing, run `scripts/poll-cost.sh` cron and pipe into spend.json.

set -uo pipefail
cat >/dev/null 2>&1 || true
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SPEND="$ROOT/.claude/spend.json"

# --- Harness budget (multi-agent runs only) ---
HARNESS_BUDGET="$ROOT/.claude/harness/budget.json"
if [ -f "$HARNESS_BUDGET" ]; then
  max=$(jq -r '.max_usd // 0' "$HARNESS_BUDGET")
  spent=$(jq -r '.spent_usd // 0' "$HARNESS_BUDGET")
  if [ -n "$max" ] && [ "$max" != "0" ]; then
    over=$(awk "BEGIN{print ($spent > $max)}" 2>/dev/null || echo "0")
    if [ "$over" = "1" ]; then
      echo "BLOCKED: harness budget exceeded ($spent / $max USD). Halt or raise HARNESS_MAX_USD." >&2
      exit 2
    fi
  fi
fi

# --- Daily cap (any session) ---
LIMIT="${HARNESS_DAILY_BUDGET_USD:-0}"
if [ "$LIMIT" != "0" ] && [ -f "$SPEND" ]; then
  today=$(date +%Y-%m-%d)
  today_spent=$(jq -r --arg d "$today" '.daily[$d] // 0' "$SPEND" 2>/dev/null || echo 0)
  over=$(awk "BEGIN{print ($today_spent > $LIMIT)}" 2>/dev/null || echo "0")
  if [ "$over" = "1" ]; then
    echo "BLOCKED: daily budget exceeded ($today_spent / $LIMIT USD today). Resume tomorrow or raise HARNESS_DAILY_BUDGET_USD." >&2
    exit 2
  fi
  # Soft warning at 80%
  warn=$(awk "BEGIN{print ($today_spent > $LIMIT * 0.8)}" 2>/dev/null || echo "0")
  if [ "$warn" = "1" ]; then
    jq -Rn --arg msg "WARNING: at 80% of daily budget ($today_spent / $LIMIT USD). Defer ambitious refactors." \
      '{hookSpecificOutput:{hookEventName:"PreToolUse",additionalContext:$msg}}'
  fi
fi

exit 0
