#!/usr/bin/env bash
# Tier 2 dogfood gate — runs the smoke spec with the full PR3 reviewer sandbox.
# Asserts every Tier 1 criterion plus: no sandbox violations, every reviewer role
# has done.marker + exit-code.txt + review.json.
#
# Pre-conditions:
#   - PR3 reviewer subagents discoverable
#   - codex CLI installed and authenticated with a model that supports
#     `--sandbox read-only` (e.g. gpt-5.5-high)
#   - clean git tree
#
# Usage:
#   ./scripts/dogfood_tier2.sh          # full pass
#   ./scripts/dogfood_tier2.sh --check  # gate assertions only
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SPEC="docs/specs/2026-05-28-dogfood-smoke.md"
EXPECTED_PHASES=2

if [ "${1:-}" != "--check" ]; then
  if [ -n "$(git status --porcelain)" ]; then
    echo "tier2: working tree dirty; commit or stash first" >&2
    exit 2
  fi
  if [ ! -f "$SPEC" ]; then
    echo "tier2: missing $SPEC" >&2
    exit 2
  fi

  unset AUTO_PILOT_DISABLE_NEW_REVIEWERS
  echo "tier2: launching headless loop on $SPEC (full reviewer sandbox)"
  python3 scripts/orchestrator.py init --spec "$SPEC" --max-workers 2 --force
  python3 scripts/headless-loop.py --max-iter 20 --timeout-build 1800 --max-cost-usd 5.0
fi

echo "tier2: running gate assertions"
python3 scripts/_dogfood_gate.py --tier 2 --repo-root "$REPO_ROOT" --phases "$EXPECTED_PHASES"
