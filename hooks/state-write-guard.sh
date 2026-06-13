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
import json, os, sys
try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("__PARSE_FAIL__")
    sys.exit(0)
ti = d.get("tool_input")
if not isinstance(ti, dict):
    print("__PARSE_FAIL__")
    sys.exit(0)
raw = ti.get("file_path", "")
# Normalize path to collapse ../ traversal before pattern matching.
# This closes the path-traversal bypass:
#   /repo/.planning/auto-pilot/../auto-pilot/state.json
# normalizes to:
#   /repo/.planning/auto-pilot/state.json  ← caught by the guard below
print(os.path.normpath(raw) if raw else "")
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

    # Extract command string — fail-closed on parse failures.
    # shellcheck disable=SC2016 # python heredoc — $ and backtick are regex literals
    verdict=$(printf '%s' "$input" | python3 -c '
import json, os, re, shlex, sys

try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("BLOCK:unparseable JSON")
    sys.exit(0)

ti = d.get("tool_input")
if not isinstance(ti, dict):
    print("BLOCK:non-dict tool_input")
    sys.exit(0)

cmd_val = ti.get("command", "")
if not isinstance(cmd_val, str):
    print("BLOCK:non-string command")
    sys.exit(0)

cmd = cmd_val

# --- 1. Eval-construct detection (mirrors branch-lock.sh strategy) ---
# Fail CLOSED on command-substitution $(...)/$VAR/${VAR}, backtick, eval,
# sh/bash/zsh -c.  Any of these in the command string is treated as a
# potential apply_to_main bypass — static analysis cannot resolve it.
# \x27 = single-quote; avoids bash string-nesting issues in this Python block.
_eval_construct = re.search(r"\$[\w({\x27\"]|`|\beval\b|\b(?:ba|z)?sh\s+-c\b", cmd)
if _eval_construct:
    print("BLOCK:eval-construct")
    sys.exit(0)

# --- 2. Normalize separators and tokenize ---
# Strip subshell / brace-group / compound-separator metacharacters so a
# wrapped invocation tokenizes the same as a bare one (mirrors branch-lock.sh).
sanitized = re.sub(r"[(){}]", " ", cmd)
sanitized = re.sub(r"&&|\|\||[;&|\n]", " ", sanitized)

try:
    tokens = shlex.split(sanitized)
except ValueError:
    # Unbalanced quotes — fail closed.
    print("BLOCK:shlex-unbalanced-quotes")
    sys.exit(0)

# --- 3. Guard git am/apply/format-patch ---
# These verbs apply patches directly to the working tree, bypassing
# WorktreeManager.apply_to_main.  git allows intermediate value-taking flags
# (-C <path>, -c <name=value>) before the subcommand; we skip those pairs
# correctly so `git -C /repo am x.mbox` is still caught.
GUARDED_VERBS = {"am", "apply", "format-patch"}
GIT_VALUE_FLAGS = {"-C", "-c"}

for i, tok in enumerate(tokens):
    basename = os.path.basename(tok)
    if basename != "git":
        continue
    j = i + 1
    while j < len(tokens):
        t = tokens[j]
        if t in GIT_VALUE_FLAGS:
            j += 2  # skip flag AND its value token
        elif t.startswith("-"):
            j += 1  # other flags (no value token)
        else:
            break   # found the subcommand
    if j < len(tokens) and tokens[j] in GUARDED_VERBS:
        print("BLOCK:git-apply-verb:" + tokens[j])
        sys.exit(0)

print("ALLOW")
')

    case "$verdict" in
      ALLOW) ;;
      BLOCK:*)
        echo "auto-pilot: BLOCKED Bash \$ROOT-mutating git verb — must go through WorktreeManager.apply_to_main (set AUTO_PILOT_ALLOW_MAIN_MUTATE=1 to override): ${verdict#BLOCK:}" >&2
        exit 2
        ;;
      *)
        # Unexpected verdict — fail closed.
        echo "auto-pilot: BLOCKED state-write-guard Bash — unexpected verdict: $verdict (fail-closed)" >&2
        exit 2
        ;;
    esac
    ;;
esac

exit 0
