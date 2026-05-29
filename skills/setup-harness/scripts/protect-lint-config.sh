#!/usr/bin/env bash
# PreToolUse(Write|Edit|MultiEdit): block linter/formatter/type config tampering.
# Agents commonly silence lint errors by editing the config instead of fixing the code.
set -euo pipefail
input="$(cat)"
file="$(jq -r '.tool_input.file_path // .tool_input.path // empty' <<< "$input")"
base="$(basename "$file")"

PROTECTED=(
  .eslintrc .eslintrc.js .eslintrc.json .eslintrc.cjs eslint.config.js eslint.config.mjs eslint.config.ts
  biome.json biome.jsonc .biomerc.json
  .prettierrc .prettierrc.json .prettierrc.js prettier.config.js prettier.config.cjs
  tsconfig.json tsconfig.base.json tsconfig.build.json
  pyproject.toml ruff.toml .ruff.toml mypy.ini setup.cfg
  .golangci.yml .golangci.yaml golangci.yml
  Cargo.toml rustfmt.toml clippy.toml
  .swiftlint.yml .swiftformat
  detekt.yml .detekt.yml
  .rubocop.yml
  lefthook.yml lefthook-local.yml .pre-commit-config.yaml
  .editorconfig
)

for p in "${PROTECTED[@]}"; do
  if [ "$base" = "$p" ]; then
    echo "BLOCKED: $file is a protected linter/type config. Fix the code, not the rule. Override only via PR with reviewer approval." >&2
    exit 2
  fi
done

exit 0
