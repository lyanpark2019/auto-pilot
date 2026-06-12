#!/usr/bin/env bash
# Advisory shellcheck on any *.sh the session writes/edits. Exit 0 always.
set -u
payload=$(cat)
file=$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    pass
')
case "$file" in
  *.sh) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0
command -v shellcheck >/dev/null 2>&1 || exit 0
if ! out=$(shellcheck -S warning "$file" 2>&1); then
  printf 'shellcheck advisory — %s:\n%s\n' "$file" "$out" >&2
fi
exit 0
