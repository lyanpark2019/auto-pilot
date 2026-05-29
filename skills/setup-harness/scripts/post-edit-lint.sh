#!/usr/bin/env bash
# PostToolUse(Write|Edit|MultiEdit): auto-format + lint + inject violations as additionalContext.
# Per-language dispatcher. Emits docs-compliant JSON for Claude to self-correct.
set -euo pipefail
input="$(cat)"
file="$(jq -r '.tool_input.file_path // .tool_input.path // empty' <<< "$input")"
[ -z "$file" ] && exit 0
[ -f "$file" ] || exit 0

emit() {
  local msg="$1"
  [ -z "$msg" ] && return
  jq -Rn --arg msg "$msg" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:$msg}}'
}

case "$file" in
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs)
    command -v biome >/dev/null || command -v npx >/dev/null || exit 0
    # Auto-fix
    npx --no biome format --write "$file" >/dev/null 2>&1 || true
    npx --no oxlint --fix "$file" >/dev/null 2>&1 || true
    # Collect remaining
    diag="$(npx --no oxlint "$file" 2>&1 | head -30 || true)"
    emit "$diag"
    ;;
  *.py)
    command -v ruff >/dev/null || exit 0
    ruff check --fix --quiet "$file" >/dev/null 2>&1 || true
    ruff format --quiet "$file" >/dev/null 2>&1 || true
    diag="$(ruff check --output-format=concise "$file" 2>&1 | head -30 || true)"
    emit "$diag"
    ;;
  *.go)
    command -v gofumpt >/dev/null && gofumpt -w "$file" >/dev/null 2>&1 || true
    diag="$(golangci-lint run --fast "$file" 2>&1 | head -30 || true)"
    emit "$diag"
    ;;
  *.rs)
    rustfmt --edition 2021 "$file" >/dev/null 2>&1 || true
    # Workspace clippy is too slow for PostToolUse; defer full lint to pre-commit
    ;;
  *.swift)
    command -v swiftformat >/dev/null && swiftformat "$file" >/dev/null 2>&1 || true
    diag="$(swiftlint lint --path "$file" --quiet 2>&1 | head -30 || true)"
    emit "$diag"
    ;;
  *.kt|*.kts)
    command -v ktlint >/dev/null && ktlint --format "$file" >/dev/null 2>&1 || true
    diag="$(detekt --input "$file" 2>&1 | head -30 || true)"
    emit "$diag"
    ;;
  *.rb)
    command -v rubocop >/dev/null && rubocop -a "$file" >/dev/null 2>&1 || true
    diag="$(rubocop --format simple "$file" 2>&1 | head -30 || true)"
    emit "$diag"
    ;;
  *)
    exit 0
    ;;
esac

exit 0
