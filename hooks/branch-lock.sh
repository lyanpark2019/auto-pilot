#!/usr/bin/env bash
# ⓓ-2 branch-lock.sh — PreToolUse Bash
# Deny `git commit` / `git push` when current branch is main or master.
# Bypass: AUTO_PILOT_MAIN_OK=1.
# Worktree-aware: uses the tool_input.cwd field when available.
# Unparseable stdin → allow (fail-open).
set -euo pipefail

deny() {
  local reason="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
    "${reason//\"/\\\"}"
  exit 0
}

payload=$(cat)

cmd=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("command") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")

# Unparseable → allow
if [[ -z "$cmd" ]] && ! printf '%s' "$payload" | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null; then
  exit 0
fi

[[ -z "$cmd" ]] && exit 0

# Only fire when command actually contains a commit or push (word boundary check).
# Tolerate git GLOBAL options before the subcommand (`git -C <path> commit`,
# `git -c k=v push`, `git --no-pager push`) — review r1: adjacency-only regex
# let those bypass the lock.
GIT_OPTS='([[:space:]]+(-C[[:space:]]+[^[:space:];|&]+|-c[[:space:]]+[^[:space:];|&]+|--[A-Za-z0-9-]+(=[^[:space:];|&]*)?))*'
has_commit=0
has_push=0
if printf '%s' "$cmd" | grep -qE "(^|[[:space:];|&])git${GIT_OPTS}[[:space:]]+commit([[:space:]]|\$)"; then
  has_commit=1
fi
if printf '%s' "$cmd" | grep -qE "(^|[[:space:];|&])git${GIT_OPTS}[[:space:]]+push([[:space:]]|\$)"; then
  has_push=1
fi

[[ "$has_commit" == "0" && "$has_push" == "0" ]] && exit 0

# Bypass
if [[ "${AUTO_PILOT_MAIN_OK:-0}" == "1" ]]; then
  exit 0
fi

# Determine working directory: use tool_input.cwd if present, else CWD
work_dir=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("cwd") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")

if [[ -z "$work_dir" ]]; then
  work_dir="$(pwd)"
fi

# Honor `git -C <path>` — the branch that matters is the -C target's, not CWD's.
# -C may appear after other global opts (`git -c a=b -C /repo commit`) — match it
# anywhere in the git invocation segment, not only immediately after `git`
# (r2 review: extraction-order bypass).
c_path=$(printf '%s' "$cmd" | grep -oE '(^|[[:space:];|&])git[[:space:]][^;|&]*-C[[:space:]]+[^[:space:];|&]+' | head -1 | sed -E 's/.*-C[[:space:]]+//' || echo "")
if [[ -n "$c_path" ]]; then
  if [[ "$c_path" == /* ]]; then
    work_dir="$c_path"
  else
    work_dir="$work_dir/$c_path"
  fi
fi

# Get current branch (tolerate non-git dirs)
current_branch=$(git -C "$work_dir" branch --show-current 2>/dev/null || echo "")

if [[ "$current_branch" == "main" || "$current_branch" == "master" ]]; then
  deny "Refusing git commit/push on protected branch '$current_branch'. Set AUTO_PILOT_MAIN_OK=1 to override."
fi

exit 0
