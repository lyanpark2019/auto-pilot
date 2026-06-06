#!/usr/bin/env bash
set -euo pipefail

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
fail() {
  echo "FAIL: $*" >&2
  exit 1
}
mkdir -p "$TMP/scripts" "$TMP/schemas" "$TMP/.claude-plugin"
cp "$REPO_ROOT/scripts/check.sh" "$TMP/scripts/check.sh"
cp "$REPO_ROOT/schemas/plugin.schema.json" "$TMP/schemas/plugin.schema.json"

write_good_manifest() {
  cat >"$TMP/.claude-plugin/plugin.json" <<'JSON'
{
  "name": "auto-pilot",
  "version": "0.1.0",
  "description": "Autonomous multi-agent swarm for dispatching, scoring, and coordinating local worker agents.",
  "author": {
    "name": "lyan",
    "email": "jyyoon@fyqro.com"
  },
  "homepage": "https://github.com/lyanpark2019/auto-pilot",
  "keywords": [
    "autonomous",
    "multi-agent",
    "swarm",
    "tmux",
    "codex",
    "self-improvement"
  ]
}
JSON
}

run_check() {
  local out="$1"
  local err="$2"
  (cd "$TMP" && bash scripts/check.sh) >"$out" 2>"$err"
}

assert_rejects() {
  local label="$1"
  local err_pattern="$2"
  local out="$TMP/$label.out"
  local err="$TMP/$label.err"

  if run_check "$out" "$err"; then
    fail "expected $label to fail"
  fi

  grep -F "FAIL plugin.json" "$err" >/dev/null || fail "$label did not report plugin failure"
  grep -E "$err_pattern" "$err" >/dev/null || fail "$label stderr did not match $err_pattern"
}

write_good_manifest
run_check "$TMP/good.out" "$TMP/good.err" || fail "expected good manifest to pass"
grep -F "OK plugin manifest" "$TMP/good.out" >/dev/null || fail "good output missed OK plugin manifest"

jq '.name = "Bad_Name"' "$TMP/.claude-plugin/plugin.json" >"$TMP/plugin.tmp"
mv "$TMP/plugin.tmp" "$TMP/.claude-plugin/plugin.json"
assert_rejects "bad-name" "name"

write_good_manifest
jq 'del(.description)' "$TMP/.claude-plugin/plugin.json" >"$TMP/plugin.tmp"
mv "$TMP/plugin.tmp" "$TMP/.claude-plugin/plugin.json"
assert_rejects "missing-description" "description"

write_good_manifest
jq '.foo = "bar"' "$TMP/.claude-plugin/plugin.json" >"$TMP/plugin.tmp"
mv "$TMP/plugin.tmp" "$TMP/.claude-plugin/plugin.json"
assert_rejects "extra-prop" "additionalProperties|foo"

echo "tests/check PASS"
