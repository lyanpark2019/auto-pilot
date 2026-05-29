#!/usr/bin/env bash
# install-drift-hook.sh — wire the doc-drift detector into a target repo's
# pre-push pipeline. Idempotent.
#
# Steps:
#   1. Copy check_doc_drift.sh -> <repo>/scripts/quality/check_doc_drift.sh (chmod +x)
#   2. Append the lefthook snippet to <repo>/lefthook.yml (creating it if absent),
#      skipping if the `drift:` command already exists.
#   3. Print next steps (lefthook install + DRIFT_FALLBACK_PREFIX hint).
#
# Pairs with templates/lefthook.yml.drift-snippet (snippet text).
# Run from setup-harness Step 4.

set -eu

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-.}"
cd "$TARGET"

# Resolve target repo root.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

# 1) copy the checker
mkdir -p scripts/quality
cp "$SKILL_DIR/scripts/check_doc_drift.sh" scripts/quality/check_doc_drift.sh
chmod +x scripts/quality/check_doc_drift.sh
printf 'installed: scripts/quality/check_doc_drift.sh\n'

# 2) wire lefthook
SNIPPET="$SKILL_DIR/templates/lefthook.yml.drift-snippet"
if [ ! -f lefthook.yml ]; then
  printf 'pre-push:\n  parallel: true\n  commands:\n' > lefthook.yml
fi
if grep -qE '^\s*drift:' lefthook.yml; then
  printf 'lefthook.yml: drift command already present, skipping append\n'
else
  cat "$SNIPPET" >> lefthook.yml
  printf 'lefthook.yml: appended drift pre-push entry\n'
fi

cat <<'EOF'

next steps:
  - run `lefthook install` to activate the git hook
  - if your project uses a module-prefix convention (e.g. docs cite `cli/x.py`
    meaning `src/myproj/cli/x.py`), export DRIFT_FALLBACK_PREFIX=src/myproj
    in lefthook.yml or your shell rc
  - smoke-test: `bash scripts/quality/check_doc_drift.sh`
EOF
