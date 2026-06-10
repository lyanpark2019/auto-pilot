#!/usr/bin/env bash
# Prune GitHub Actions run history for this repo, keeping the most recent N runs.
#
# Usage:
#   bash scripts/ci/prune_action_runs.sh            # keep 4 (default), dry-run
#   bash scripts/ci/prune_action_runs.sh --apply    # actually delete
#   bash scripts/ci/prune_action_runs.sh --keep 10 --apply
#
# Guards:
#   - refuses to run unless the active gh account is lyanpark2019 (publish identity)
#   - dry-run by default; --apply required to delete
set -euo pipefail

KEEP=4
APPLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP="$2"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

case "$KEEP" in
  ''|*[!0-9]*) echo "--keep must be a non-negative integer, got: $KEEP" >&2; exit 2 ;;
esac

ACTIVE=$(gh api user --jq .login 2>/dev/null || true)
if [ "$ACTIVE" != "lyanpark2019" ]; then
  echo "BLOCKED: active gh account is '$ACTIVE', expected 'lyanpark2019'." >&2
  echo "Fix: gh auth switch --hostname github.com --user lyanpark2019" >&2
  exit 2
fi

REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
echo "repo=$REPO keep=$KEEP apply=$APPLY"

# Runs beyond the newest $KEEP, newest-first ordering from the API.
DOOMED=$(gh api "repos/$REPO/actions/runs?per_page=100" --paginate \
  --jq '.workflow_runs[].id' | tail -n "+$((KEEP + 1))")

if [ -z "$DOOMED" ]; then
  echo "nothing to prune (total runs <= $KEEP)"
  exit 0
fi

COUNT=$(printf '%s\n' "$DOOMED" | wc -l | tr -d ' ')
echo "runs to delete: $COUNT"

if [ "$APPLY" -ne 1 ]; then
  printf '%s\n' "$DOOMED" | head -10
  [ "$COUNT" -gt 10 ] && echo "... ($((COUNT - 10)) more)"
  echo "dry-run — pass --apply to delete"
  exit 0
fi

printf '%s\n' "$DOOMED" | while IFS= read -r run_id; do
  gh api -X DELETE "repos/$REPO/actions/runs/$run_id" >/dev/null \
    && echo "deleted $run_id" \
    || echo "FAILED to delete $run_id" >&2
done
echo "prune complete (kept newest $KEEP)"
