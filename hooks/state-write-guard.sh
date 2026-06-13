#!/usr/bin/env bash
# state-write-guard.sh — PreToolUse Edit|Write|MultiEdit|Bash
#
# Enforces two invariants from CLAUDE.md rules-for-this-plugin:
#   1. state.json writes must go through _state.save_state (not direct Edit/Write)
#   2. $ROOT mutations via git am/apply/format-patch must go through
#      WorktreeManager.apply_to_main, not direct Bash invocation.
#
# Detection: active only under AUTO_PILOT_SUBAGENT_ROLE=worker|codex-reviewer|claude-reviewer
# (mirrors pre-reviewer-write.sh env-gate pattern).  Unset or unknown role → exit 0.
# Bypass envs: AUTO_PILOT_ALLOW_STATE_WRITE=1 (Edit/Write), AUTO_PILOT_ALLOW_MAIN_MUTATE=1 (Bash).
# Fail-closed on parse error (unparseable JSON or missing tool_name → exit 2).
# Fail-open on any other internal error (guard errors → exit 0, logged to stderr).
set -uo pipefail

role="${AUTO_PILOT_SUBAGENT_ROLE:-}"
case "$role" in
  worker|codex-reviewer|claude-reviewer|review-gatekeeper) ;;
  *) exit 0 ;;
esac

input=$(cat)

tool_name=$(printf '%s' "$input" | python3 -c '
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
  echo "auto-pilot: BLOCKED state-write-guard — unparseable or missing tool_name (fail-closed)" >&2
  exit 2
fi

case "$tool_name" in
  Edit|Write|MultiEdit)
    if [ "${AUTO_PILOT_ALLOW_STATE_WRITE:-}" = "1" ]; then
      exit 0
    fi

    file_path=$(printf '%s' "$input" | python3 -c '
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
      echo "auto-pilot: BLOCKED state-write-guard $tool_name — unparseable or non-dict tool_input (fail-closed)" >&2
      exit 2
    fi

    # Only the canonical loop-state file path is guarded (rel + any-abs-prefix).
    # A broad */state.json glob would false-deny unrelated fixtures.
    case "$file_path" in
      */.planning/auto-pilot/state.json|.planning/auto-pilot/state.json)
        echo "auto-pilot: BLOCKED Edit/Write to state.json ($file_path) — writes must go through _state.save_state (set AUTO_PILOT_ALLOW_STATE_WRITE=1 to override)" >&2
        exit 2
        ;;
      *) exit 0 ;;
    esac
    ;;

  Bash)
    # Bypass honored ONLY from the real process/session env, NOT a command-string
    # prefix: a tool-call prefix never reaches this hook's env and accepting the
    # literal token would make the guard self-grantable by any subagent (SEC5 class).
    if [ "${AUTO_PILOT_ALLOW_MAIN_MUTATE:-}" = "1" ]; then
      exit 0
    fi

    cmd=$(printf '%s' "$input" | python3 -c '
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
cmd_val = ti.get("command", "")
if not isinstance(cmd_val, str):
    print("__PARSE_FAIL__")
    sys.exit(0)
print(cmd_val)
')

    if [ "$cmd" = "__PARSE_FAIL__" ]; then
      echo "auto-pilot: BLOCKED state-write-guard Bash — unparseable or non-dict tool_input (fail-closed)" >&2
      exit 2
    fi

    # Guard git am / apply / format-patch: these verbs apply patches directly to
    # the working tree, bypassing WorktreeManager.apply_to_main.
    # git allows intermediate -flag [value] pairs (e.g. `git -C /repo am x.mbox`),
    # so the regex allows zero or more flag+optional-value groups before the verb.
    # ACCEPTED TRADEOFF: `git apply --check`/`--stat` and `git format-patch` are
    # technically read-only; guarded here anyway as manual apply_to_main-bypass
    # attempts.  Set AUTO_PILOT_ALLOW_MAIN_MUTATE=1 for the rare legit manual case.
    re_main='(/[^ ]*/)?git([[:space:]]+-[^[:space:]]+([[:space:]]+[^[:space:]]+)?)*[[:space:]]+(am|apply|format-patch)([[:space:]]|$)'
    if printf '%s' "$cmd" | grep -qE "(^|[[:space:]]|/)$re_main"; then
      echo "auto-pilot: BLOCKED Bash \$ROOT-mutating git verb — must go through WorktreeManager.apply_to_main (set AUTO_PILOT_ALLOW_MAIN_MUTATE=1 to override): $cmd" >&2
      exit 2
    fi
    ;;
esac

exit 0
