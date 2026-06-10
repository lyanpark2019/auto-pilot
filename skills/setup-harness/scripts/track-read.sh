#!/usr/bin/env bash
# PreToolUse(Read): record every evidence read to .claude/.evidence-reads
# Paired with verify-gate.sh — agent must Read evidence before claiming a test passed.
# Pattern from anthropics/cwc-long-running-agents (Apache-2.0, Copyright Anthropic PBC).
# Reimplementation of the pattern — no upstream text retained.
set -uo pipefail
input="$(cat 2>/dev/null || echo '{}')"
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
EVID="$ROOT/.claude/.evidence-reads"

file=$(jq -r '.tool_input.file_path // empty' <<< "$input" 2>/dev/null)
[ -z "$file" ] && exit 0

# Only track evidence files: screenshots, console logs, test outputs
case "$file" in
  *.png|*.jpg|*.jpeg|*.gif|*.webp|*.log|*test-results*|*screenshot*|*evidence*|*coverage*)
    mkdir -p "$(dirname "$EVID")" 2>/dev/null
    echo "$(date +%s) $file" >> "$EVID"
    ;;
esac
exit 0
