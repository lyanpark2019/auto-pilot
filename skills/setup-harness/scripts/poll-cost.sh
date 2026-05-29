#!/usr/bin/env bash
# Poll Anthropic Admin API for today's cost and update .claude/spend.json.
# Run via cron every 5–15 min:
#   */10 * * * * cd /project && bash .claude/scripts/poll-cost.sh
#
# Requires: ANTHROPIC_ADMIN_KEY env var (sk-ant-admin-...), curl, jq
# No webhook exists in 2026 — polling is the only option.
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SPEND="$ROOT/.claude/spend.json"
KEY="${ANTHROPIC_ADMIN_KEY:-}"

[ -z "$KEY" ] && { echo "ANTHROPIC_ADMIN_KEY not set"; exit 1; }

today=$(date +%Y-%m-%d)
yday=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)

# Anthropic Admin API: cost report endpoint
resp=$(curl -sS -m 30 \
  -H "x-api-key: $KEY" \
  -H "anthropic-version: 2023-06-01" \
  "https://api.anthropic.com/v1/organizations/cost_report?start_date=$yday&end_date=$today" 2>&1)

# Parse total cost for today
today_cost=$(echo "$resp" | jq -r --arg d "$today" '.data[] | select(.date==$d) | .total_cost // 0' 2>/dev/null || echo 0)

# Update spend.json
mkdir -p "$(dirname "$SPEND")"
[ -f "$SPEND" ] || echo '{"daily":{}}' > "$SPEND"
jq --arg d "$today" --argjson c "$today_cost" \
  '.daily[$d] = $c | .updated = now | .updated_iso = (now | strftime("%Y-%m-%dT%H:%M:%SZ"))' \
  "$SPEND" > "$SPEND.tmp" && mv "$SPEND.tmp" "$SPEND"

echo "Updated $today spend: \$$today_cost"
