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
# Capture the matched `git <global-opts> <subcommand>` segment so -C extraction
# below can be scoped to GLOBAL OPTIONS ONLY — r3 review: extracting -C from the
# whole command let a `-C` token inside a commit MESSAGE hijack the branch-check
# target (false-allow on main).
git_seg=""
if seg=$(printf '%s' "$cmd" | grep -oE "(^|[[:space:];|&])git${GIT_OPTS}[[:space:]]+commit([[:space:]]|\$)" | head -1) && [[ -n "$seg" ]]; then
  has_commit=1
  git_seg="$seg"
fi
if seg=$(printf '%s' "$cmd" | grep -oE "(^|[[:space:];|&])git${GIT_OPTS}[[:space:]]+push([[:space:]]|\$)" | head -1) && [[ -n "$seg" ]]; then
  has_push=1
  [[ -z "$git_seg" ]] && git_seg="$seg"
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
# Extraction is scoped to $git_seg (global-opts segment captured above), so a
# `-C` token in the commit message can never hijack the target (r3 finding).
# -C may follow other global opts (`git -c a=b -C /repo commit` — r2 finding).
# Residual: multiple -C compose in git (`-C /a -C b` = /a/b); we take the last
# one only — compound relative -C chains are out of scope.
c_path=$(printf '%s' "$git_seg" | grep -oE '(^|[[:space:]])-C[[:space:]]+[^[:space:];|&]+' | tail -1 | sed -E 's/.*-C[[:space:]]+//' || echo "")
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
