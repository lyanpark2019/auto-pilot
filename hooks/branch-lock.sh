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

# STRATEGY SHIFT (r4): three rounds of "pick the right segment" patches each
# spawned a new ordering edge (r2 opt-order, r3 message -C, r4 push-first
# chain). Segment SELECTION is abolished: collect EVERY `git <global-opts>
# commit|push` invocation in the command and deny if ANY of them targets a
# protected branch — order-independent by construction.
segs=$(printf '%s' "$cmd" | grep -oE "(^|[[:space:];|&])git${GIT_OPTS}[[:space:]]+(commit|push)([[:space:]]|\$)" || echo "")

[[ -z "$segs" ]] && exit 0

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

# Per segment: honor its own `git -C <path>` (the branch that matters is the
# -C target's, not CWD's). -C extraction stays scoped to the matched
# global-opts segment, so commit-message tokens can never hijack it (r3).
# Residual (documented, accepted): multiple -C compose in git (`-C /a -C b`
# = /a/b) — we honor the last one only.
while IFS= read -r seg; do
  [[ -z "$seg" ]] && continue
  c_path=$(printf '%s' "$seg" | grep -oE '(^|[[:space:]])-C[[:space:]]+[^[:space:];|&]+' | tail -1 | sed -E 's/.*-C[[:space:]]+//' || echo "")
  target="$work_dir"
  if [[ -n "$c_path" ]]; then
    if [[ "$c_path" == /* ]]; then
      target="$c_path"
    else
      target="$work_dir/$c_path"
    fi
  fi
  # Get this invocation's branch (tolerate non-git dirs)
  branch=$(git -C "$target" branch --show-current 2>/dev/null || echo "")
  if [[ "$branch" == "main" || "$branch" == "master" ]]; then
    deny "Refusing git commit/push on protected branch '$branch' (target: $target). Set AUTO_PILOT_MAIN_OK=1 to override."
  fi
done <<< "$segs"

exit 0
