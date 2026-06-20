#!/usr/bin/env bash
# xreview — one-command cross-model adversarial review of a repo's working-tree change.
#
# Runs the `xmodel-review` Archon workflow (Claude + Codex both review the same diff) against
# a target git repo and prints the merged report. No learning loop, no state — a pure review.
#
# Usage:
#   xreview.sh [<repo-dir>]      # default: current directory
#
# Requires: the Archon engine checkout (ARCHON_ROOT) + codex auth (~/.codex/auth.json) and a
# logged-in Claude (CLAUDE_USE_GLOBAL_AUTH=1 uses it). The workflow must be discoverable —
# install.sh copies xmodel-review.yaml into ~/.archon/workflows/.
set -euo pipefail

ARCHON_ROOT="${ARCHON_ROOT:-/Users/lyan/Documents/Project/archon}"
WORKFLOW="xmodel-review"
TARGET="${1:-$PWD}"

[ -d "$ARCHON_ROOT" ] || { echo "xreview: archon engine not found at $ARCHON_ROOT (set ARCHON_ROOT)" >&2; exit 1; }
[ -d "$TARGET/.git" ] || { echo "xreview: $TARGET is not a git repo" >&2; exit 1; }
TARGET_ABS="$(cd "$TARGET" && pwd)"

export CLAUDE_USE_GLOBAL_AUTH=1
export ARCHON_SUPPRESS_NESTED_CLAUDE_WARNING=1
ARCHON_BUN="${ARCHON_BUN:-bun}"

echo "xreview: cross-model review of $TARGET_ABS" >&2
(
  cd "$ARCHON_ROOT"
  "$ARCHON_BUN" run cli workflow run "$WORKFLOW" --cwd "$TARGET_ABS"
)

# Print the merge node's report (newest matching artifact; no hardcoded run-id).
REVIEW_DIRS=(
  "$TARGET_ABS/.archon/artifacts/runs"
  "$HOME/.archon/projects"
)
for root in "${REVIEW_DIRS[@]}"; do
  [ -d "$root" ] || continue
  merge="$(find "$root" -type f -name "merge.json" -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -n 1 || true)"
  if [ -n "$merge" ]; then
    echo "--- merge.json ($merge) ---" >&2
    cat "$merge"; echo
    break
  fi
done
