#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Post-merge layout: swarm machinery under swarm/, agents at plugin top level.
RUBRIC="swarm/scripts/prompts/_RUBRIC.md"
SCORE="swarm/scripts/prompts/pm-score.md"
VERIFY="swarm/scripts/prompts/pm-verify.md"
VERIFIER="agents/swarm-verifier.md"

DIMS=(
  correctness
  scope_discipline
  test_coverage
  code_quality
  alignment_with_acceptance
)

FILES=("$RUBRIC" "$SCORE" "$VERIFY" "$VERIFIER")

for dim in "${DIMS[@]}"; do
  for file in "${FILES[@]}"; do
    if ! grep -Fq "$dim" "$file"; then
      echo "MISSING $dim in $file" >&2
      exit 1
    fi
  done
done

# Assert verdict-band integers in _RUBRIC.md
for band in 40 25 24; do
  if ! grep -Fq "$band" "$RUBRIC"; then
    echo "MISSING verdict band $band in $RUBRIC" >&2
    exit 1
  fi
done

# Assert hard-rule strings in _RUBRIC.md (case-insensitive)
if ! grep -iq "alignment_with_acceptance=3" "$RUBRIC"; then
  echo "MISSING hard rule 'alignment_with_acceptance=3' in $RUBRIC" >&2
  exit 1
fi

if ! grep -iq "empty diff" "$RUBRIC"; then
  echo "MISSING hard rule 'empty diff' in $RUBRIC" >&2
  exit 1
fi

echo "rubric coherence OK"
exit 0
