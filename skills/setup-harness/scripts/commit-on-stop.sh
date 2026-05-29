#!/usr/bin/env bash
# Stop hook: auto-commit any uncommitted progress at session end.
# Provides the cross-session continuity Anthropic's harness depends on (git log = source of truth).
# Pattern from anthropics/cwc-long-running-agents.
set -uo pipefail
input="$(cat 2>/dev/null || echo '{}')"
[ "$(jq -r '.stop_hook_active // false' <<< "$input")" = "true" ] && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT" 2>/dev/null || exit 0

# Skip if no changes
git diff --quiet --cached 2>/dev/null && git diff --quiet 2>/dev/null && exit 0

# Auto-commit on Stop is gated by env var (opt-in)
if [ "${HARNESS_AUTOCOMMIT_ON_STOP:-0}" != "1" ]; then
  # Just notify, don't commit
  changed=$(git diff --name-only 2>/dev/null | head -5 | tr '\n' ',' | sed 's/,$//')
  jq -Rn --arg msg "Uncommitted changes at Stop: $changed. Set HARNESS_AUTOCOMMIT_ON_STOP=1 to auto-commit, or commit manually." \
    '{hookSpecificOutput:{hookEventName:"Stop",additionalContext:$msg}}'
  exit 0
fi

# Auto-commit (opt-in)
session_id="${CLAUDE_SESSION_ID:-$(date +%s)}"
git add -u 2>/dev/null  # only modify/delete tracked files; never adds new untracked
git commit -m "wip: harness checkpoint $session_id" 2>/dev/null || true
exit 0
