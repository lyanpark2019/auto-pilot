#!/usr/bin/env bash
# auto-pilot pre-bash guard: block known-bad patterns.
# - interactive TUI in non-interactive shell (claude doctor etc.)
# - ruff --fix without --diff on composition root paths
# - chained Cloudflare SSL changes without intermediate verify
#
# Reads tool input from stdin (JSON), inspects command, exits 2 to deny.

set -uo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    # Blocking guard: unparseable stdin must deny, not skip.
    sys.stderr.write("auto-pilot: BLOCKED malformed tool_input json (fail-closed)\n")
    sys.exit(2)
# Valid JSON but no command key → allow (not a parse failure).
val = d.get("tool_input") or {}
print(val.get("command", "") if isinstance(val, dict) else "")
')
# Propagate exit 2 from the python parse-fail sentinel.
_cmd_rc=$?
if [ "$_cmd_rc" -eq 2 ]; then
  exit 2
fi

[[ -z "$cmd" ]] && exit 0

# Bypass switch
if [[ "${AUTO_PILOT_BASH_BYPASS:-0}" == "1" ]]; then
  exit 0
fi

# Rule 1: interactive TUI
case "$cmd" in
  *"claude doctor"*)
    echo "auto-pilot: BLOCKED 'claude doctor' — interactive TUI, hangs in non-interactive shell. Use 'claude --version' + manual diagnostic instead." >&2
    exit 2
    ;;
esac

# Rule 2: ruff --fix on composition root (very specific — bulk fix on __init__)
if echo "$cmd" | grep -qE 'ruff[[:space:]]+(check[[:space:]]+)?--fix' ; then
  if echo "$cmd" | grep -qE '__init__\.py|composition_root|wiring\.py|container\.py' ; then
    echo "auto-pilot: BLOCKED 'ruff --fix' on composition root. Use --diff first, or set AUTO_PILOT_BASH_BYPASS=1 after reviewing." >&2
    exit 2
  fi
fi

# Rule 3: chained Cloudflare SSL changes (&& between two SSL config calls)
if echo "$cmd" | grep -qE 'ssl[_-]?mode|min_tls_version' ; then
  ssl_count=$(echo "$cmd" | grep -oE 'ssl[_-]?mode|min_tls_version' | wc -l | tr -d ' ')
  if [[ "$ssl_count" -gt 1 ]]; then
    echo "auto-pilot: BLOCKED chained SSL config changes. Apply ONE at a time and verify site is up before the next. Set AUTO_PILOT_BASH_BYPASS=1 to override." >&2
    exit 2
  fi
fi

exit 0
