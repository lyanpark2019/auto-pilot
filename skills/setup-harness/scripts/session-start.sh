#!/usr/bin/env bash
# SessionStart: inject current branch + recent git activity + PROGRESS.json into agent context.
# Standardizes the "where did I leave off" routine across sessions.
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT" 2>/dev/null || exit 0

# Adaptive verbosity based on effort.level (passed from Claude Code via stdin)
input="$(cat 2>/dev/null || echo '{}')"
effort=$(jq -r '.effort.level // "medium"' <<< "$input" 2>/dev/null || echo "medium")

if [ "$effort" = "low" ]; then
  # Minimal context for cheap sessions
  ctx="branch: $(git branch --show-current 2>/dev/null || echo '?'), HEAD: $(git rev-parse --short HEAD 2>/dev/null || echo '?')"
else
  ctx="$(
    echo "=== Session start context ==="
    echo "Working dir: $ROOT"
    echo "Branch: $(git branch --show-current 2>/dev/null || echo '?')"
    echo ""
    echo "=== Recent commits (10) ==="
    git log --oneline -10 2>/dev/null || echo "(no git history)"
    echo ""
    echo "=== Uncommitted changes ==="
    git status -s 2>/dev/null | head -20 || echo "(clean)"
    echo ""
    if [ -f "$ROOT/.claude/PROGRESS.json" ]; then
      echo "=== PROGRESS.json ==="
      cat "$ROOT/.claude/PROGRESS.json"
    fi
  )"
fi

jq -Rn --arg msg "$ctx" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$msg}}'
