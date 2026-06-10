#!/usr/bin/env bash
# PreToolUse(*): user-controlled kill switch for the autonomous loop.
# Touch .claude/AGENT_STOP to halt — every subsequent tool call exits 2.
# Pattern from anthropics/cwc-long-running-agents (Apache-2.0, Copyright Anthropic PBC).
# Reimplementation of the pattern — no upstream text retained.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
if [ -f "$ROOT/.claude/AGENT_STOP" ]; then
  echo "BLOCKED: kill switch active (.claude/AGENT_STOP exists). Delete it to resume." >&2
  exit 2
fi
exit 0
