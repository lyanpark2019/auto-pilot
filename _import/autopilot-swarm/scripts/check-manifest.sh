#!/usr/bin/env bash
set -euo pipefail

# Determine manifest path: optional arg > repo root > script-relative fallback
if [[ $# -ge 1 ]]; then
  MANIFEST="$1"
else
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || dirname "$(dirname "$(realpath "$0")")")"
  MANIFEST="${REPO_ROOT}/.claude-plugin/plugin.json"
fi

fail() { echo "FAIL: $*" >&2; exit 1; }

command -v jq >/dev/null 2>&1 || fail "jq not found on PATH"
[[ -f "$MANIFEST" ]] || fail "manifest not found: $MANIFEST"

# Parse entire manifest once
JSON="$(cat "$MANIFEST")"

# ---------- required fields ----------

# name: non-empty string
NAME="$(printf '%s' "$JSON" | jq -r '.name // empty')"
[[ -n "$NAME" ]] || fail "required field 'name' is missing or empty"
TYPE="$(printf '%s' "$JSON" | jq -r '.name | type')"
[[ "$TYPE" == "string" ]] || fail "'name' must be a string, got $TYPE"

# version: string matching semver-ish pattern
VERSION="$(printf '%s' "$JSON" | jq -r '.version // empty')"
[[ -n "$VERSION" ]] || fail "required field 'version' is missing or empty"
TYPE="$(printf '%s' "$JSON" | jq -r '.version | type')"
[[ "$TYPE" == "string" ]] || fail "'version' must be a string, got $TYPE"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-].*)?$ ]] || fail "'version' does not match semver pattern: $VERSION"

# description: non-empty string
DESC="$(printf '%s' "$JSON" | jq -r '.description // empty')"
[[ -n "$DESC" ]] || fail "required field 'description' is missing or empty"
TYPE="$(printf '%s' "$JSON" | jq -r '.description | type')"
[[ "$TYPE" == "string" ]] || fail "'description' must be a string, got $TYPE"

# ---------- optional fields ----------

# author.name: string
if printf '%s' "$JSON" | jq -e '.author.name != null' >/dev/null 2>&1; then
  TYPE="$(printf '%s' "$JSON" | jq -r '.author.name | type')"
  [[ "$TYPE" == "string" ]] || fail "'author.name' must be a string, got $TYPE"
fi

# author.email: string matching .+@.+\..+
if printf '%s' "$JSON" | jq -e '.author.email != null' >/dev/null 2>&1; then
  TYPE="$(printf '%s' "$JSON" | jq -r '.author.email | type')"
  [[ "$TYPE" == "string" ]] || fail "'author.email' must be a string, got $TYPE"
  EMAIL="$(printf '%s' "$JSON" | jq -r '.author.email')"
  [[ "$EMAIL" =~ .+@.+\..+ ]] || fail "'author.email' invalid format: $EMAIL"
fi

# homepage: string starting with http
if printf '%s' "$JSON" | jq -e '.homepage != null' >/dev/null 2>&1; then
  TYPE="$(printf '%s' "$JSON" | jq -r '.homepage | type')"
  [[ "$TYPE" == "string" ]] || fail "'homepage' must be a string, got $TYPE"
  HP="$(printf '%s' "$JSON" | jq -r '.homepage')"
  [[ "$HP" == http* ]] || fail "'homepage' must start with http: $HP"
fi

# keywords: array of strings
if printf '%s' "$JSON" | jq -e '.keywords != null' >/dev/null 2>&1; then
  TYPE="$(printf '%s' "$JSON" | jq -r '.keywords | type')"
  [[ "$TYPE" == "array" ]] || fail "'keywords' must be an array, got $TYPE"
  # each element must be a string
  BAD="$(printf '%s' "$JSON" | jq -r '.keywords[] | select(type != "string")' 2>/dev/null | wc -l | tr -d ' ')"
  [[ "$BAD" -eq 0 ]] || fail "'keywords' contains non-string element(s)"
fi

# ---------- unknown top-level keys (warn only) ----------
KNOWN='["name","version","description","author","homepage","keywords"]'
UNKNOWN="$(printf '%s' "$JSON" | jq -r --argjson known "$KNOWN" 'keys[] | select(. as $k | $known | index($k) == null)')"
if [[ -n "$UNKNOWN" ]]; then
  echo "WARN: unknown top-level key(s): $(echo "$UNKNOWN" | tr '\n' ' ')" >&2
fi

echo "OK: ${NAME}@${VERSION}"
