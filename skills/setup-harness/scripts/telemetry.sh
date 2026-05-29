#!/usr/bin/env bash
# Telemetry hook: stream every hook event into .claude/logs/audit.jsonl + optional OTLP.
# Non-blocking, fire-and-forget. Register on PostToolUse, Stop, SessionEnd, SubagentStop.
#
# OTLP endpoint: set OTEL_EXPORTER_OTLP_LOGS_ENDPOINT to enable cloud export.
# Without it, only local jsonl is written.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LOG="$ROOT/.claude/logs/audit.jsonl"
mkdir -p "$(dirname "$LOG")" 2>/dev/null

EVENT=$(cat 2>/dev/null || echo '{}')
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
SID="${CLAUDE_SESSION_ID:-unknown}"

# Enrich event with timestamp + session_id + host
ENRICHED=$(jq -c --arg ts "$TS" --arg sid "$SID" --arg host "${HOSTNAME:-$(hostname)}" \
  '. + {ts: $ts, session_id: $sid, host: $host}' <<<"$EVENT" 2>/dev/null || echo "$EVENT")

# 1. Local jsonl (always)
echo "$ENRICHED" >> "$LOG"

# 2. OTLP export (optional, 1s timeout, fire-and-forget)
if [ -n "${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT:-}" ]; then
  curl -sS -m 1 -X POST "${OTEL_EXPORTER_OTLP_LOGS_ENDPOINT}/v1/logs" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --argjson body "$ENRICHED" --arg ts "$TS" '{
      resourceLogs: [{
        resource: {attributes: [{key: "service.name", value: {stringValue: "claude-code"}}]},
        scopeLogs: [{logRecords: [{
          timeUnixNano: (now * 1e9 | tostring),
          body: {stringValue: ($body | tostring)}
        }]}]
      }]
    }')" >/dev/null 2>&1 || true &
fi

exit 0
