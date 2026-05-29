#!/usr/bin/env bash
# Stop hook: browser-app E2E smoke gate. Block "done" until a Playwright CLI
# smoke run passes. Prefers Playwright CLI over Playwright MCP (4x cheaper context).
#
# bootstrap.sh auto-registers this Stop hook when it detects a Playwright dep in
# package.json (STACK_BROWSER). Throttled like stop-quality-gate.sh and no-ops
# cleanly (exit 0) when there is no package.json / no Playwright / nothing dirty,
# so it is harmless even if registered in a non-browser project.
set -euo pipefail
input="$(cat)"
[ "$(jq -r '.stop_hook_active // false' <<< "$input")" = "true" ] && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
LAST_RUN="$ROOT/.claude/.e2e-last-run"
THROTTLE="${E2E_THROTTLE_SEC:-600}"
NOW=$(date +%s)
if [ -f "$LAST_RUN" ]; then
  LAST=$(cat "$LAST_RUN" 2>/dev/null || echo 0)
  [ "$((NOW - LAST))" -lt "$THROTTLE" ] && exit 0
fi

cd "$ROOT"

# Only browser apps. Require package.json with a playwright dep.
[ -f package.json ] || exit 0
jq -e '.devDependencies["@playwright/test"] // .dependencies["@playwright/test"] // .devDependencies.playwright // .dependencies.playwright' \
  package.json >/dev/null 2>&1 || exit 0

# Only run when there is something to check.
DIRTY=$(git diff --name-only --diff-filter=AM 2>/dev/null || true)
[ -z "$DIRTY" ] && exit 0

fail() {
  jq -Rn --arg msg "$1" '{decision:"block",reason:$msg}'
  exit 0
}

# Prefer an explicit "test:smoke" npm script; else run @smoke-tagged Playwright tests.
if jq -e '.scripts["test:smoke"]' package.json >/dev/null 2>&1; then
  npm run --silent test:smoke 2>&1 | tail -40 || fail "Playwright smoke (test:smoke) failed — fix before completing."
elif command -v npx >/dev/null 2>&1; then
  npx --no-install playwright test --grep @smoke 2>&1 | tail -40 || fail "Playwright @smoke run failed — fix before completing."
else
  exit 0
fi

echo "$NOW" > "$LAST_RUN"
exit 0
