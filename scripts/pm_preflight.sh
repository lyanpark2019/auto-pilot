#!/usr/bin/env bash
# pm_preflight.sh — run before each dispatch phase.
#
# Collects repo state, verifies GitHub user, and writes a preflight artifact
# conforming to schemas/preflight.schema.json at:
#   .planning/auto-pilot/preflight/phase-<N>.json
#
# Usage:
#   bash scripts/pm_preflight.sh --phase <N>
#
# The artifact is required by prepare_subagent_ticket (_dispatch.py):
#   - absent → PreflightError
#   - generated_ts older than 900 s → PreflightError (re-run required)
#   - phase key mismatch → PreflightError
#   - head_sha != current HEAD → PreflightError (stale, re-run)
#
# GitHub user mapping table (data block — NOT a generic rule):
#   Sewhoan/*      → Sewhoan
#   lyanpark2019/* → lyanpark2019
#   default        → <origin owner itself>
#
# On gh-user mismatch: auto-switch via `gh auth switch` then re-verify.
# Exit codes: 0 = ok, 1 = error, 2 = model-routing.yaml invalid.

set -euo pipefail

PHASE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --phase) PHASE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$PHASE" ]]; then
  echo "Usage: bash scripts/pm_preflight.sh --phase <N>" >&2
  exit 1
fi

# ── repo_root ─────────────────────────────────────────────────────────────────
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "error: not inside a git repository" >&2
  exit 1
}

# ── branch ────────────────────────────────────────────────────────────────────
BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"

# ── head_sha ──────────────────────────────────────────────────────────────────
HEAD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"

# ── worktree_clean ────────────────────────────────────────────────────────────
STATUS_OUT="$(git -C "$REPO_ROOT" status --porcelain)"
if [[ -z "$STATUS_OUT" ]]; then
  WORKTREE_CLEAN="True"
else
  WORKTREE_CLEAN="False"
fi

# ── GitHub user mapping ───────────────────────────────────────────────────────
# Data block — one entry per rule; NOT a generic rule engine.
ORIGIN_URL="$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || echo "")"

_map_gh_user() {
  local url="$1"
  # Rule 1: Sewhoan/* → Sewhoan
  if echo "$url" | grep -qE '(github\.com[:/])Sewhoan/'; then
    echo "Sewhoan"; return
  fi
  # Rule 2: lyanpark2019/* → lyanpark2019
  if echo "$url" | grep -qE '(github\.com[:/])lyanpark2019/'; then
    echo "lyanpark2019"; return
  fi
  # Default: extract owner from URL
  echo "$url" | sed -E 's|.*github\.com[:/]([^/]+)/.*|\1|'
}

EXPECTED_GH_USER="$(_map_gh_user "$ORIGIN_URL")"

# ── actual_gh_user ────────────────────────────────────────────────────────────
_get_actual_gh_user() {
  if command -v gh >/dev/null 2>&1; then
    gh api user -q .login 2>/dev/null || \
      gh auth status 2>&1 | grep -oE 'Logged in to github.com account [^ ]+' \
        | awk '{print $NF}' || echo "unknown"
  else
    echo "unknown"
  fi
}

ACTUAL_GH_USER="$(_get_actual_gh_user)"

# ── auto-switch on mismatch ───────────────────────────────────────────────────
if [[ "$ACTUAL_GH_USER" != "$EXPECTED_GH_USER" ]] && \
   [[ "$EXPECTED_GH_USER" != "unknown" ]] && \
   [[ "$ACTUAL_GH_USER" != "unknown" ]]; then
  echo "gh user mismatch: expected=$EXPECTED_GH_USER actual=$ACTUAL_GH_USER — attempting auto-switch" >&2
  if command -v gh >/dev/null 2>&1; then
    gh auth switch --hostname github.com --user "$EXPECTED_GH_USER" 2>/dev/null || true
    ACTUAL_GH_USER="$(_get_actual_gh_user)"
    if [[ "$ACTUAL_GH_USER" != "$EXPECTED_GH_USER" ]]; then
      echo "warning: gh auth switch did not fully succeed; actual=$ACTUAL_GH_USER" >&2
    fi
  fi
fi

# ── model-routing.yaml validity ──────────────────────────────────────────────
python3 -c "import sys; sys.path.insert(0,'$REPO_ROOT/scripts'); import _routing; _routing.codex_timeouts()" || {
  echo "BLOCKED: model-routing.yaml invalid or unreadable" >&2
  exit 2
}

# ── tool_versions ─────────────────────────────────────────────────────────────
_ver() { "$@" --version 2>/dev/null | head -1 || echo "unavailable"; }
PY_VER="$(_ver python3)"
GIT_VER="$(_ver git)"
CODEX_VER="$(codex --version 2>/dev/null | head -1 || echo null)"
CLAUDE_VER="$(claude --version 2>/dev/null | head -1 || echo null)"

# ── generated_ts ──────────────────────────────────────────────────────────────
GENERATED_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ── write artifact ────────────────────────────────────────────────────────────
PREFLIGHT_DIR="$REPO_ROOT/.planning/auto-pilot/preflight"
mkdir -p "$PREFLIGHT_DIR"
ARTIFACT_PATH="$PREFLIGHT_DIR/phase-${PHASE}.json"

# Build JSON using python3 (safe quoting)
python3 - <<PYEOF
import json, sys
artifact = {
    "repo_root":        "$REPO_ROOT",
    "branch":           "$BRANCH",
    "head_sha":         "$HEAD_SHA",
    "worktree_clean":   $WORKTREE_CLEAN,
    "expected_gh_user": "$EXPECTED_GH_USER",
    "actual_gh_user":   "$ACTUAL_GH_USER",
    "tool_versions": {
        "python3": "$PY_VER",
        "git":     "$GIT_VER",
        "codex":   None if "$CODEX_VER" == "null" else "$CODEX_VER",
        "claude":  None if "$CLAUDE_VER" == "null" else "$CLAUDE_VER",
    },
    "generated_ts": "$GENERATED_TS",
    "phase":        $PHASE,
}
path = "$ARTIFACT_PATH"
with open(path, "w") as f:
    json.dump(artifact, f, indent=2, sort_keys=True)
    f.write("\n")
print(json.dumps({"ok": True, "artifact": path, "phase": $PHASE,
                  "head_sha": "$HEAD_SHA", "actual_gh_user": "$ACTUAL_GH_USER"}, indent=2))
PYEOF
