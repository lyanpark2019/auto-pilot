#!/usr/bin/env bash
# worker-scope-gate.sh — PreToolUse Edit|Write|MultiEdit
# When AUTO_PILOT_SUBAGENT_ROLE=worker AND AUTO_PILOT_SCOPE_FILES is set,
# deny any edit whose file_path is not in the scope list.
# No-op when role != worker or when AUTO_PILOT_SCOPE_FILES is unset.
# Fail-closed on unparseable payload (mirrors pre-reviewer-write.sh pattern).
set -uo pipefail

role="${AUTO_PILOT_SUBAGENT_ROLE:-}"
if [ "$role" != "worker" ]; then
  exit 0
fi

scope_files="${AUTO_PILOT_SCOPE_FILES:-}"
if [ -z "$scope_files" ]; then
  exit 0
fi

input=$(cat)

file_path=$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("__PARSE_FAIL__")
    sys.exit(0)
val = (d.get("tool_input") or {}).get("file_path", "")
if not isinstance(val, str):
    print("__PARSE_FAIL__")
    sys.exit(0)
print(val)
')

if [ "$file_path" = "__PARSE_FAIL__" ]; then
  echo "auto-pilot: BLOCKED worker — unparseable payload (fail-closed)" >&2
  exit 2
fi

if [ -z "$file_path" ]; then
  exit 0
fi

# Check if file_path is in the scope list (newline- or space-separated).
# Convert scope_files to a newline-separated stream for portable word-splitting.
in_scope=$(printf '%s' "$scope_files" | tr ' ' '\n' | python3 -c '
import sys, os
allowed = [l.strip() for l in sys.stdin if l.strip()]
target = sys.argv[1]
# Normalise: strip leading ./ for comparison
def norm(p):
    return os.path.normpath(p)
if norm(target) in [norm(a) for a in allowed]:
    print("yes")
else:
    print("no")
' "$file_path")

if [ "$in_scope" = "yes" ]; then
  exit 0
fi

echo "auto-pilot: BLOCKED worker — $file_path not in scope allowlist" >&2
exit 2
