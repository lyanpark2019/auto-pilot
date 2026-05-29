#!/usr/bin/env bash
# PreCompact: persist load-bearing state before context compaction.
# Compaction drops middle conversation; save current task state to PROGRESS.json so it survives.
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
PROGRESS="$ROOT/.claude/PROGRESS.json"
[ -f "$PROGRESS" ] || echo '{}' > "$PROGRESS"

# Stamp last-compact timestamp; agent can read and rebuild from git log + this file
jq --arg ts "$(date -Iseconds)" \
   --arg branch "$(git branch --show-current 2>/dev/null || echo '?')" \
   '. + {last_compact:$ts, branch_at_compact:$branch}' \
   "$PROGRESS" > "$PROGRESS.tmp" && mv "$PROGRESS.tmp" "$PROGRESS"

exit 0
