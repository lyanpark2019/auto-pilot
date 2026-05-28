#!/usr/bin/env bash
# Tier 1 dogfood gate — runs the smoke spec with new reviewer subagents DISABLED.
# PM falls back to general-purpose dispatch. Asserts PR1 (contract) + PR2 (worktree)
# acceptance criteria only; PR3 (reviewer sandbox) deliberately not exercised.
#
# Pre-conditions:
#   - run from auto-pilot repo root
#   - clean git tree
#   - claude CLI on PATH
#
# Usage:
#   ./scripts/dogfood_tier1.sh          # full pass
#   ./scripts/dogfood_tier1.sh --check  # gate assertions only (assumes spec already ran)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SPEC="docs/specs/2026-05-28-dogfood-smoke.md"
EXPECTED_PHASES=2

if [ "${1:-}" != "--check" ]; then
  if [ -n "$(git status --porcelain)" ]; then
    echo "tier1: working tree dirty; commit or stash first" >&2
    exit 2
  fi
  if [ ! -f "$SPEC" ]; then
    echo "tier1: missing $SPEC" >&2
    exit 2
  fi

  export AUTO_PILOT_DISABLE_NEW_REVIEWERS=1
  echo "tier1: launching headless loop on $SPEC (reviewer fallback mode)"
  python3 scripts/orchestrator.py init --spec "$SPEC" --max-workers 2 --force
  python3 scripts/headless-loop.py --max-iter 20 --timeout-build 1800 --max-cost-usd 5.0
fi

echo "tier1: running gate assertions"
python3 scripts/_dogfood_gate.py --tier 1 --repo-root "$REPO_ROOT" --phases "$EXPECTED_PHASES"
