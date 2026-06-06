#!/usr/bin/env bash
# ⓓ-3 deletion-diff-guard.sh — PreToolUse Bash
# On `git push` commands: deny when deletions > 500 AND deletions > 3× insertions.
# Bypass: AUTO_PILOT_BIG_DELETE_OK=1.
# No upstream → allow (first push).
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

# Only fire on git push
if ! printf '%s' "$cmd" | grep -qE '(^|[[:space:];|&])git[[:space:]]+push([[:space:]]|$)'; then
  exit 0
fi

# Bypass — hook env OR an explicit env-prefix on the command itself. The hook
# process inherits the SESSION env, so `AUTO_PILOT_BIG_DELETE_OK=1 git push`
# typed as a tool call never reaches the env check below; accept the literal
# prefix in the command string as the operator-intent signal (r3 fix).
if [[ "${AUTO_PILOT_BIG_DELETE_OK:-0}" == "1" ]]; then
  exit 0
fi
if printf '%s' "$cmd" | grep -q 'AUTO_PILOT_BIG_DELETE_OK=1'; then
  exit 0
fi

# Determine working directory
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

# Check if upstream exists — no upstream → allow (first push)
if ! git -C "$work_dir" rev-parse '@{u}' &>/dev/null; then
  # Try origin/<branch> as fallback
  branch=$(git -C "$work_dir" branch --show-current 2>/dev/null || echo "")
  if [[ -z "$branch" ]] || ! git -C "$work_dir" rev-parse "origin/$branch" &>/dev/null; then
    exit 0
  fi
  upstream_ref="origin/$branch"
else
  upstream_ref="@{u}"
fi

# Compute shortstat with timeout
shortstat=$(timeout 8 git -C "$work_dir" diff --shortstat "${upstream_ref}..HEAD" 2>/dev/null || echo "")

if [[ -z "$shortstat" ]]; then
  exit 0
fi

# Parse insertions and deletions from shortstat output
# Format: " 3 files changed, 120 insertions(+), 890 deletions(-)"
insertions=$(printf '%s' "$shortstat" | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+' || echo "0")
deletions=$(printf '%s' "$shortstat" | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+' || echo "0")

insertions="${insertions:-0}"
deletions="${deletions:-0}"

if [[ "$deletions" -gt 500 ]]; then
  # Check deletions > 3× insertions
  threshold=$(( insertions * 3 ))
  if [[ "$deletions" -gt "$threshold" ]]; then
    deny "Large deletion detected: ${deletions} deletions vs ${insertions} insertions (>${threshold} threshold). Set AUTO_PILOT_BIG_DELETE_OK=1 to override."
  fi
fi

exit 0
