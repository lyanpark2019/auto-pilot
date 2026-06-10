#!/usr/bin/env bash
# auto-pilot reviewer sandbox: blocks reviewer agents from writing outside
# their CONTRACT_DIR/outputs/<role>/ scope or running mutation commands.
#
# Detection: PM sets AUTO_PILOT_SUBAGENT_ROLE in the spawned subagent env.
# When unset, hook is a no-op for non-reviewer dispatches (worker, etc.).
set -uo pipefail

role="${AUTO_PILOT_SUBAGENT_ROLE:-}"
case "$role" in
  codex-reviewer|claude-reviewer|review-gatekeeper|tech-critic-lead) ;;
  *) exit 0 ;;
esac

input=$(cat)
allowed_output_dir="${AUTO_PILOT_OUTPUT_DIR:-}"
if [ -z "$allowed_output_dir" ]; then
  echo "auto-pilot: AUTO_PILOT_OUTPUT_DIR unset for reviewer role $role" >&2
  exit 2
fi

tool_name=$(echo "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("__PARSE_FAIL__")
    sys.exit(0)
val = d.get("tool_name", "")
if not isinstance(val, str) or not val:
    print("__PARSE_FAIL__")
    sys.exit(0)
print(val)
')

if [ "$tool_name" = "__PARSE_FAIL__" ] || [ -z "$tool_name" ]; then
  echo "auto-pilot: BLOCKED reviewer ($role) — unparseable or missing tool_name (fail-closed)" >&2
  exit 2
fi

case "$tool_name" in
  Edit|Write|MultiEdit)
    file_path=$(echo "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("__PARSE_FAIL__")
    sys.exit(0)
ti = d.get("tool_input")
if not isinstance(ti, dict):
    print("__PARSE_FAIL__")
    sys.exit(0)
print(ti.get("file_path", ""))
')
    if [ "$file_path" = "__PARSE_FAIL__" ]; then
      echo "auto-pilot: BLOCKED reviewer ($role) $tool_name — unparseable or non-dict tool_input (fail-closed)" >&2
      exit 2
    fi
    case "$file_path" in
      "$allowed_output_dir"/*) exit 0 ;;
      *)
        echo "auto-pilot: BLOCKED reviewer ($role) $tool_name to $file_path (allowed: $allowed_output_dir/)" >&2
        exit 2 ;;
    esac
    ;;
  Bash)
    cmd=$(echo "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("__PARSE_FAIL__")
    sys.exit(0)
ti = d.get("tool_input")
if not isinstance(ti, dict):
    # DEFECT 2: a non-dict tool_input (e.g. a string) must fail-closed, not
    # silently yield an empty command that the grep below never matches.
    print("__PARSE_FAIL__")
    sys.exit(0)
cmd_val = ti.get("command", "")
if not isinstance(cmd_val, str):
    # A non-string command (list/dict) would str()-render to a form the grep
    # below never matches → mutation slips through.  Fail-closed (codex
    # re-review 2026-06-10).
    print("__PARSE_FAIL__")
    sys.exit(0)
print(cmd_val)
')
    if [ "$cmd" = "__PARSE_FAIL__" ]; then
      echo "auto-pilot: BLOCKED reviewer ($role) Bash — unparseable or non-dict tool_input (fail-closed)" >&2
      exit 2
    fi
    if echo "$cmd" | grep -qE '(^|[[:space:]])(git[[:space:]]+(commit|push|reset|checkout|stash|am|rebase|merge|worktree|restore|clean)|rm[[:space:]]|mv[[:space:]]|chmod[[:space:]]|chown[[:space:]]|tee[[:space:]]|sed[[:space:]]+-i|awk[[:space:]]+-i|curl[[:space:]]|wget[[:space:]]|ssh[[:space:]]|scp[[:space:]]|rsync[[:space:]])'; then
      echo "auto-pilot: BLOCKED reviewer ($role) Bash mutation: $cmd" >&2
      exit 2
    fi
    if echo "$cmd" | grep -qE '(^|[[:space:]])codex([[:space:]]|$)'; then
      if ! echo "$cmd" | grep -qE -- '--sandbox[[:space:]]+read-only'; then
        echo "auto-pilot: BLOCKED codex invocation without --sandbox read-only: $cmd" >&2
        exit 2
      fi
    fi
    ;;
esac
exit 0
