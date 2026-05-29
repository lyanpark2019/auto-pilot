#!/usr/bin/env bash
# Stop hook: block "done" until lint+type+tests pass.
# Detects stack automatically. Throttled to avoid burning time on each Stop.
set -euo pipefail
input="$(cat)"
[ "$(jq -r '.stop_hook_active // false' <<< "$input")" = "true" ] && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LAST_RUN="$ROOT/.claude/.qg-last-run"
THROTTLE="${QG_THROTTLE_SEC:-300}"
NOW=$(date +%s)
if [ -f "$LAST_RUN" ]; then
  LAST=$(cat "$LAST_RUN" 2>/dev/null || echo 0)
  [ "$((NOW - LAST))" -lt "$THROTTLE" ] && exit 0
fi

cd "$ROOT"

# Run only if dirty
DIRTY=$(git diff --name-only --diff-filter=AM 2>/dev/null || true)
[ -z "$DIRTY" ] && exit 0

fail() {
  jq -Rn --arg msg "$1" '{decision:"block",reason:$msg}'
  exit 0
}

# Per-stack gates
if [ -f pyproject.toml ] || [ -f requirements.txt ]; then
  command -v ruff >/dev/null && { ruff check . 2>&1 | head -20 || fail "ruff failed"; }
  command -v mypy >/dev/null && { mypy . 2>&1 | head -20 || fail "mypy failed"; }
  command -v pytest >/dev/null && { pytest -x -q 2>&1 | tail -30 || fail "pytest failed"; }
fi

if [ -f package.json ]; then
  if jq -e '.scripts.lint' package.json >/dev/null 2>&1; then
    npm run lint --silent 2>&1 | tail -30 || fail "npm run lint failed"
  fi
  if jq -e '.scripts.typecheck // .scripts["type-check"]' package.json >/dev/null 2>&1; then
    npm run typecheck --silent 2>&1 | tail -30 || npm run type-check --silent 2>&1 | tail -30 || fail "typecheck failed"
  fi
  if jq -e '.scripts.test' package.json >/dev/null 2>&1; then
    npm test --silent 2>&1 | tail -30 || fail "npm test failed"
  fi
fi

if [ -f go.mod ]; then
  go vet ./... 2>&1 | head -20 || fail "go vet failed"
  go test ./... 2>&1 | tail -30 || fail "go test failed"
fi

if [ -f Cargo.toml ]; then
  cargo clippy --quiet 2>&1 | head -20 || fail "clippy failed"
  cargo test --quiet 2>&1 | tail -30 || fail "cargo test failed"
fi

echo "$NOW" > "$LAST_RUN"
exit 0
