#!/usr/bin/env bash
# headless-sync-dispatch-guard.sh — PreToolUse(Task|Bash)
# Under HARNESS_HEADLESS=1 the PM session must dispatch subagents SYNCHRONOUSLY:
# a background dispatch can be orphaned when the headless session exits between
# iterations (F-6, run 2). Deny run_in_background=true in headless mode.
#
# Residual: Bash backgrounding via a trailing `&` is not detected (would need
# fuzzy command parsing) — deliberately out of scope.
# Unparseable stdin → allow (fail-open repo convention).
set -euo pipefail

deny() {
  local reason="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
    "${reason//\"/\\\"}"
  exit 0
}

# Only act in headless mode.
[[ "${HARNESS_HEADLESS:-}" != "1" ]] && exit 0

payload=$(cat)

bg=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print("1" if (d.get("tool_input") or {}).get("run_in_background") is True else "0")
except Exception:
    print("err")
' 2>/dev/null || echo "err")

[[ "$bg" == "err" ]] && exit 0  # fail-open

if [[ "$bg" == "1" ]]; then
  deny "Headless mode (HARNESS_HEADLESS=1) forbids run_in_background dispatch: a backgrounded subagent is orphaned when the session exits between iterations. Dispatch synchronously."
fi

exit 0
