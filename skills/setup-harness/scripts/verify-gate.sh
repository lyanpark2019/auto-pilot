#!/usr/bin/env bash
# PreToolUse(Write|Edit): Default-FAIL gate for test-results.json and similar criteria files.
# Block writes claiming "passes": true unless the agent has Read an evidence file this session.
# Pattern from anthropics/cwc-long-running-agents (March 2026 harness).
set -uo pipefail
input="$(cat 2>/dev/null || echo '{}')"
ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
EVID="$ROOT/.claude/.evidence-reads"

file=$(jq -r '.tool_input.file_path // .tool_input.path // empty' <<< "$input" 2>/dev/null)
[ -z "$file" ] && exit 0

# Only gate test-results.json and harness sprint eval files
case "$file" in
  *test-results.json|*test-results.yaml|*.claude/harness/sprints/*eval.md|*PROGRESS.json) ;;
  *) exit 0 ;;
esac

# Inspect content being written
new_content=$(jq -r '.tool_input.new_string // .tool_input.content // empty' <<< "$input" 2>/dev/null)

# If claiming a pass, require recent evidence read
if echo "$new_content" | grep -qE '"passes"[[:space:]]*:[[:space:]]*true|verdict[[:space:]]*:[[:space:]]*"?PASS|status.*completed'; then
  if [ ! -s "$EVID" ]; then
    echo "BLOCKED: Default-FAIL gate. No evidence file Read this session. Open a screenshot/log/test output before claiming PASS." >&2
    exit 2
  fi
  # Check at least one read was within last 60s (current task evidence)
  now=$(date +%s)
  recent=$(awk -v t="$now" 'BEGIN{f=0} ($1 > t-60){f=1} END{print f}' "$EVID")
  if [ "$recent" != "1" ]; then
    echo "BLOCKED: evidence reads are stale (>60s). Re-open the evidence file before claiming PASS." >&2
    exit 2
  fi
  # Consume the token: clear evidence
  : > "$EVID"
fi

exit 0
