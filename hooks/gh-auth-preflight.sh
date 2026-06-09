#!/usr/bin/env bash
# ⓓ-4 gh-auth-preflight.sh — PreToolUse Bash
# Verify correct gh user is active before any `gh ` command (except `gh auth`).
# Expected user derived from git remote origin URL owner mapping:
#   Sewhoan/*       → Sewhoan
#   lyanpark2019/*  → lyanpark2019
#   else            → owner (first path component)
# SoT: same table lives in scripts/pm_preflight.sh (contract β); this is a copy.
# Active user cached in $TMPDIR/gh-auth-<owner>.cache for 300s.
# Mismatch → deny with exact fix command.
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
  printf '[hook:gh-auth-preflight] fail-open: unparseable stdin\n' >&2
  exit 0
fi

[[ -z "$cmd" ]] && exit 0

# Fire only when some segment's FIRST token is exactly `gh`.
# Split on ; && || | newline ( to get simple-command segments, then check
# whether any segment's leading token is `gh`.  This prevents false-fires
# from substrings inside comments, strings, or other command args.
# shellcheck disable=SC2016 # python heredoc — not a shell expansion context
gh_segment=$(printf '%s' "$cmd" | python3 -c '
import sys, re
cmd = sys.stdin.read()
# Split on compound separators; strip leading whitespace per segment.
segments = re.split(r";|&&|\|\||[|\n(]", cmd)
gh_seg = ""
for seg in segments:
    tokens = seg.split()
    if not tokens:
        continue
    # Skip leading env-var assignments (VAR=val or VAR=) before first-token check.
    start = 0
    while start < len(tokens) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[start]):
        start += 1
    if start >= len(tokens):
        continue
    if tokens[start] == "gh":
        gh_seg = seg.strip()
        break
print(gh_seg)
' 2>/dev/null || echo "")

if [[ -z "$gh_segment" ]]; then
  exit 0
fi

# Skip `gh auth` commands (maintenance, not repo operations).
# When the command is `gh auth switch`, purge owner cache files so the next
# gh command re-validates against the newly active user (cache invalidation).
if printf '%s' "$gh_segment" | grep -qE '^gh[[:space:]]+auth[[:space:]]'; then
  if printf '%s' "$gh_segment" | grep -qE '^gh[[:space:]]+auth[[:space:]]+switch'; then
    rm -f "${TMPDIR:-/tmp}"/gh-auth-*.cache 2>/dev/null || true
  fi
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
[[ -z "$work_dir" ]] && work_dir="$(pwd)"

# Get git remote origin URL to determine expected owner
remote_url=$(git -C "$work_dir" remote get-url origin 2>/dev/null || echo "")

# Extract owner from URL (handles https://github.com/owner/repo and git@github.com:owner/repo)
owner=$(printf '%s' "$remote_url" | python3 -c '
import sys, re
url = sys.stdin.read().strip()
# git@github.com:owner/repo.git  or  https://github.com/owner/repo.git
m = re.search(r"github\.com[:/]([^/]+)/", url)
print(m.group(1) if m else "")
' 2>/dev/null || echo "")

if [[ -z "$owner" ]]; then
  printf '[hook:gh-auth-preflight] fail-open: cannot determine repo owner from remote URL\n' >&2
  exit 0
fi

# Owner → expected user mapping (SoT mirror of scripts/pm_preflight.sh)
case "$owner" in
  Sewhoan)       expected_user="Sewhoan" ;;
  lyanpark2019)  expected_user="lyanpark2019" ;;
  *)             expected_user="$owner" ;;
esac

# Cache file for active gh user (keyed by owner, TTL 300s)
cache_file="${TMPDIR:-/tmp}/gh-auth-${owner}.cache"
active_user=""

if [[ -f "$cache_file" ]]; then
  # mtime via python3: GNU stat treats `-f` as filesystem mode (prints mount point,
  # exit 0) so a BSD-first fallback chain breaks on Linux — CI run 27076577146.
  cache_mtime=$(python3 -c 'import os,sys; print(int(os.stat(sys.argv[1]).st_mtime))' "$cache_file" 2>/dev/null || echo 0)
  cache_age=$(( $(date +%s) - cache_mtime ))
  if [[ "$cache_age" -lt 300 ]]; then
    active_user=$(cat "$cache_file" 2>/dev/null || echo "")
  fi
fi

if [[ -z "$active_user" ]]; then
  active_user=$(timeout 5 gh api user -q .login 2>/dev/null || echo "")
  if [[ -n "$active_user" ]]; then
    printf '%s' "$active_user" > "$cache_file"
  fi
fi

if [[ -z "$active_user" ]]; then
  printf '[hook:gh-auth-preflight] fail-open: gh not available or not authenticated\n' >&2
  exit 0
fi

if [[ "$active_user" != "$expected_user" ]]; then
  deny "gh active user '$active_user' does not match expected '$expected_user' for repo owner '$owner'. Fix: gh auth switch --hostname github.com --user $expected_user"
fi

exit 0
