#!/usr/bin/env bash
# install_doc_hooks.sh — install LOCAL git hooks for doc-management freshness gates.
#
# Installs into the CURRENT repo (must be run from the repo root or any subdir):
#   post-commit  → graphify update + advisory freshness check (prints, never blocks)
#   pre-push     → blocking freshness check (exit 1 if any doc is STALE)
#
# Idempotent: appends the guard block only if the marker is absent.
# No global install — hooks live in .git/hooks/ of the current repo.
#
# Usage: bash install_doc_hooks.sh [REPO_ROOT]

set -euo pipefail

REPO_ROOT="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
HOOK_DIR="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOK_DIR" ]; then
  echo "ERROR: $HOOK_DIR not found — is this a git repo?" >&2
  exit 1
fi

# Resolve freshness script: prefer repo-local copy, fall back to plugin
_PLUGIN_FRESHNESS="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/auto-pilot}/skills/doc-management/scripts/check_design_doc_freshness.py"
_REPO_FRESHNESS="$REPO_ROOT/scripts/doc-management/check_design_doc_freshness.py"
if [ -f "$_REPO_FRESHNESS" ]; then
  FRESHNESS_SCRIPT="$_REPO_FRESHNESS"
else
  FRESHNESS_SCRIPT="$_PLUGIN_FRESHNESS"
fi

# ── helpers ──────────────────────────────────────────────────────────────────

append_or_create() {
  local hook_file="$1"
  local marker="$2"
  local block="$3"

  if [ -f "$hook_file" ]; then
    if grep -qF "$marker" "$hook_file" 2>/dev/null; then
      echo "  SKIP $hook_file — marker already present"
      return
    fi
    # Append block to existing hook
    printf "\n%s\n" "$block" >> "$hook_file"
    echo "  APPEND $hook_file"
  else
    # Create new hook with shebang
    printf '#!/usr/bin/env bash\n%s\n' "$block" > "$hook_file"
    chmod +x "$hook_file"
    echo "  CREATE $hook_file"
  fi
  chmod +x "$hook_file"
}

# ── post-commit ───────────────────────────────────────────────────────────────

POST_COMMIT_MARKER="# doc-management: post-commit advisory"
POST_COMMIT_BLOCK="$POST_COMMIT_MARKER
# graphify update (advisory — never blocks commit)
if command -v graphify >/dev/null 2>&1; then
  graphify update . --no-cluster >/dev/null 2>&1 && echo '[doc-management] graphify graph updated' || echo '[doc-management] WARN: graphify update failed'
fi
# L3 freshness check (advisory — exit 0 regardless)
_PY=\"\$(command -v python3 || true)\"
if [ -n \"\$_PY\" ] && [ -f \"$FRESHNESS_SCRIPT\" ]; then
  \"\$_PY\" \"$FRESHNESS_SCRIPT\" docs 2>&1 | grep -E '^(STALE|WARN|freshness:)' || true
fi"

append_or_create "$HOOK_DIR/post-commit" "$POST_COMMIT_MARKER" "$POST_COMMIT_BLOCK"

# ── pre-push ──────────────────────────────────────────────────────────────────

PRE_PUSH_MARKER="# doc-management: pre-push blocking freshness gate"
PRE_PUSH_BLOCK="$PRE_PUSH_MARKER
_PY=\"\$(command -v python3 || true)\"
if [ -n \"\$_PY\" ] && [ -f \"$FRESHNESS_SCRIPT\" ]; then
  if ! \"\$_PY\" \"$FRESHNESS_SCRIPT\" docs; then
    echo '[doc-management] BLOCKED: stale design docs detected — run MAINTAIN mode before pushing'
    exit 1
  fi
fi"

append_or_create "$HOOK_DIR/pre-push" "$PRE_PUSH_MARKER" "$PRE_PUSH_BLOCK"

echo "install_doc_hooks: done"
echo "  post-commit: graphify update + advisory freshness"
echo "  pre-push:    blocking freshness gate (exit 1 on STALE)"
echo "  freshness script: $FRESHNESS_SCRIPT"
