#!/usr/bin/env bash
# Compute weekly metrics from .claude/logs/audit.jsonl.
# Run via cron weekly or on demand: bash .claude/scripts/weekly-metrics.sh
set -euo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LOG="$ROOT/.claude/logs/audit.jsonl"

[ -f "$LOG" ] || { echo "no audit log yet at $LOG"; exit 0; }

echo "=== Weekly metrics (last 7 days) ==="
echo ""

# Filter to last 7 days
WEEK_AGO=$(date -u -v-7d +%Y-%m-%dT00:00:00Z 2>/dev/null || date -u -d "7 days ago" +%Y-%m-%dT00:00:00Z)

echo "--- Tool-call volume per session ---"
jq -s --arg cutoff "$WEEK_AGO" '
  map(select(.ts >= $cutoff)) |
  group_by(.session_id) |
  map({
    session_id: .[0].session_id,
    calls: length,
    tools: (map(.tool_name) | unique)
  }) | sort_by(-.calls) | .[:10]
' "$LOG"
echo ""

echo "--- Hook trigger rate (per-minute spike check) ---"
jq -r --arg cutoff "$WEEK_AGO" \
  'select(.ts >= $cutoff) | .ts[:16]' "$LOG" | sort | uniq -c | sort -rn | head -5
echo ""

echo "--- Same-file thrash (Edit/Write > 3x in session) ---"
jq -r --arg cutoff "$WEEK_AGO" '
  select(.ts >= $cutoff) |
  select(.tool_name == "Edit" or .tool_name == "Write") |
  [.session_id, .tool_input.file_path] | @tsv
' "$LOG" 2>/dev/null | sort | uniq -c | awk '$1 > 3' | head -10
echo ""

echo "--- Most-touched files this week ---"
jq -r --arg cutoff "$WEEK_AGO" '
  select(.ts >= $cutoff) |
  select(.tool_name == "Edit" or .tool_name == "Write") |
  .tool_input.file_path
' "$LOG" 2>/dev/null | sort | uniq -c | sort -rn | head -10
echo ""

if [ -f "$ROOT/.claude/spend.json" ]; then
  echo "--- Daily spend (last 7d) ---"
  jq --arg cutoff "$WEEK_AGO" \
    '.daily | to_entries | sort_by(.key) | reverse | .[:7]' \
    "$ROOT/.claude/spend.json"
fi
