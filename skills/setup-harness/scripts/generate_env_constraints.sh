#!/usr/bin/env bash
# generate_env_constraints.sh — emit a ## Environment Constraints markdown block for a target repo.
# Usage: bash generate_env_constraints.sh [REPO_PATH]
# Output goes to stdout; caller redirects to a file or appends to SKILL output.
# Build-only this round (W2 ⓔ); apply runs are W3. PickL-API excluded → W4-1.

set -euo pipefail

REPO="${1:-.}"
REPO="$(cd "${REPO}" && pwd)"

emit() { printf '%s\n' "$@"; }

emit "## Environment Constraints"
emit ""

# --- Shell ---
SHELL_PROG="${SHELL:-$(command -v bash 2>/dev/null || echo unknown)}"
emit "**Shell:** \`${SHELL_PROG}\`"

# --- Userland: BSD vs GNU ---
if sed --version 2>/dev/null | grep -q GNU; then
  USERLAND="GNU"
else
  USERLAND="BSD (macOS/FreeBSD)"
fi
emit "**Userland:** ${USERLAND}"

OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
emit "**OS:** \`${OS_NAME}\`"
emit ""

# --- Pinned tool versions ---
emit "**Tool versions (pinned at bootstrap):**"
emit ""
emit "| Tool | Version |"
emit "|------|---------|"

_ver() {
  local cmd="$1" flag="${2:---version}"
  if command -v "${cmd}" >/dev/null 2>&1; then
    local v
    v="$("${cmd}" ${flag} 2>&1 | head -1 | tr -d '\r')"
    emit "| \`${cmd}\` | \`${v}\` |"
  fi
}

_ver python3 --version
_ver node --version
_ver git --version

# ruff: prefer .venv if present in REPO
if [ -x "${REPO}/.venv/bin/ruff" ]; then
  v="$("${REPO}/.venv/bin/ruff" --version 2>&1 | head -1)"
  emit "| \`ruff (.venv)\` | \`${v}\` |"
elif command -v ruff >/dev/null 2>&1; then
  _ver ruff --version
fi

emit ""

# --- CI runner topology ---
WORKFLOW_DIR="${REPO}/.github/workflows"
if [ -d "${WORKFLOW_DIR}" ]; then
  emit "**CI runner topology** (from \`.github/workflows/\`):"
  emit ""
  # grep runs-on values, deduplicate
  RUNNERS=$(grep -rh 'runs-on' "${WORKFLOW_DIR}" 2>/dev/null \
    | sed 's/.*runs-on:[[:space:]]*//' \
    | tr -d '"'"'" \
    | sort -u)
  if [ -n "${RUNNERS}" ]; then
    while IFS= read -r runner; do
      emit "- \`${runner}\`"
    done <<< "${RUNNERS}"
  else
    emit "- (no runs-on entries found)"
  fi
else
  emit "**CI:** no \`.github/workflows/\` detected"
fi

emit ""
