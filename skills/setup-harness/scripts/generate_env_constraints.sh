#!/usr/bin/env bash
# generate_env_constraints.sh — emit a ## Environment Constraints markdown block for a target repo.
# Usage:
#   bash generate_env_constraints.sh [REPO_PATH]                 # stdout (marker-wrapped)
#   bash generate_env_constraints.sh [REPO_PATH] --into <FILE>   # idempotent upsert
# --into replaces the existing marker-delimited block (or appends one if absent),
# so re-running never duplicates the header (review r1: bare `>> CLAUDE.md`
# duplicated the block on every run, contradicting the skill's Idempotent claim).
# Build-only this round (W2 ⓔ); apply runs are W3. PickL-API excluded → W4-1.

set -euo pipefail

REPO="${1:-.}"
REPO="$(cd "${REPO}" && pwd)"

INTO=""
if [[ "${2:-}" == "--into" ]]; then
  INTO="${3:?--into requires a target file path}"
fi

BEGIN_MARK="<!-- ENV-CONSTRAINTS:BEGIN (generate_env_constraints.sh — managed block, do not edit inside) -->"
END_MARK="<!-- ENV-CONSTRAINTS:END -->"

_generate() {
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
}

CONTENT="$(_generate)"
BLOCK="$(printf '%s\n%s\n%s' "$BEGIN_MARK" "$CONTENT" "$END_MARK")"

if [[ -z "$INTO" ]]; then
  printf '%s\n' "$BLOCK"
  exit 0
fi

# Idempotent upsert into $INTO
if [[ -f "$INTO" ]] && grep -qF "$BEGIN_MARK" "$INTO"; then
  BLOCK="$BLOCK" python3 - "$INTO" <<'PYEOF'
import os, sys

path = sys.argv[1]
block = os.environ["BLOCK"]
begin = block.splitlines()[0]
end = block.splitlines()[-1]

text = open(path, encoding="utf-8").read()
start = text.index(begin)
try:
    stop = text.index(end, start) + len(end)
except ValueError:
    # BEGIN without END = hand-corrupted managed block. Refuse cleanly rather
    # than traceback (r2 review) — file left untouched.
    sys.exit(
        f"env-constraints: BEGIN marker found in {path} but END marker missing "
        "— repair or delete the managed block, then re-run."
    )
open(path, "w", encoding="utf-8").write(text[:start] + block + text[stop:])
PYEOF
else
  { [[ -s "$INTO" ]] && printf '\n'; printf '%s\n' "$BLOCK"; } >> "$INTO"
fi
echo "env-constraints: upserted into $INTO" >&2
