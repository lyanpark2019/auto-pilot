#!/usr/bin/env bash
# PreToolUse hook: block notebooklm deletes unless explicitly confirmed.
# Wired twice in hooks/hooks.json:
#   matcher "Bash"                       → inspect tool_input.command for the CLI form
#   matcher "mcp__notebooklm__delete.*"  → MCP payloads carry the tool's own args and
#                                          NO "command" key; gate on tool_name alone
#                                          (reading only .command made this fail-open).
# Without NBM_DELETE_CONFIRMED=1 → permissionDecision deny (JSON contract, exit 0).
# Unparseable stdin → allow (hooks are non-blocking by default per CLAUDE.md).
set -euo pipefail

payload=$(cat)
tool_name=$(printf '%s' "$payload" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("tool_name") or "")' 2>/dev/null || echo "")
cmd=$(printf '%s' "$payload" | python3 -c 'import sys,json; d=json.load(sys.stdin); print((d.get("tool_input") or {}).get("command") or "")' 2>/dev/null || echo "")

deny() {
  cat <<'JSON'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Destructive: notebooklm delete blocked. Set NBM_DELETE_CONFIRMED=1 after explicit user confirmation per CLAUDE.md Destructive Action Protocol."}}
JSON
  exit 0
}

# MCP shape — tool_name like mcp__notebooklm__delete_notebook. The
# NBM_DELETE_CONFIRMED check applies unconditionally; no "command" key needed.
case "$tool_name" in
  mcp__notebooklm__*delete*)
    if [[ "${NBM_DELETE_CONFIRMED:-0}" != "1" ]]; then
      deny
    fi
    ;;
esac

# Bash CLI shape.
if [[ "$cmd" == *"notebooklm notebook delete"* ]] || [[ "$cmd" == *"notebooklm nb delete"* ]]; then
  if [[ "${NBM_DELETE_CONFIRMED:-0}" != "1" ]]; then
    deny
  fi
fi
exit 0
