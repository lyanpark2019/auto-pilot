#!/usr/bin/env bash
# PreToolUse hook: block `notebooklm notebook delete` unless explicit confirm flag set.
# Reads JSON from stdin. If command contains "notebooklm notebook delete" without env var NBM_DELETE_CONFIRMED=1, exit 2 (block).
set -euo pipefail

payload=$(cat)
cmd=$(printf '%s' "$payload" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("command",""))' 2>/dev/null || echo "")

if [[ "$cmd" == *"notebooklm notebook delete"* ]] || [[ "$cmd" == *"notebooklm nb delete"* ]]; then
  if [[ "${NBM_DELETE_CONFIRMED:-0}" != "1" ]]; then
    cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Destructive: notebooklm delete blocked. Set NBM_DELETE_CONFIRMED=1 after explicit user confirmation per CLAUDE.md Destructive Action Protocol."}}
JSON
    exit 0
  fi
fi
exit 0
