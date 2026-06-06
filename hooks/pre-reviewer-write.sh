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
except json.JSONDecodeError:
    sys.exit(0)
print(d.get("tool_name", ""))
')

case "$tool_name" in
  Edit|Write|MultiEdit)
    file_path=$(echo "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.exit(0)
print(d.get("tool_input", {}).get("file_path", ""))
')
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
except json.JSONDecodeError:
    sys.exit(0)
print(d.get("tool_input", {}).get("command", ""))
')
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
