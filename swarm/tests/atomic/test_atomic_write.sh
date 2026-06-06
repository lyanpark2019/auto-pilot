#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

source "$REPO_ROOT/scripts/lib/atomic.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_mode_0600() {
  local path="$1"
  local mode
  mode="$(stat -f '%Lp' "$path" 2>/dev/null || stat -c '%a' "$path")"
  [ "$mode" = "600" ] || fail "expected $path mode 0600, got $mode"
}

test_rejects_invalid_json() {
  local dir target
  dir="$(mktemp -d)"
  target="$dir/invalid.json"

  if printf '{"broken":' | atomic_write_json "$target" 2>/dev/null; then
    fail "invalid JSON was accepted"
  fi

  [ ! -e "$target" ] || fail "target was created for invalid JSON"
  rm -rf "$dir"
}

test_writes_valid_json_with_private_mode() {
  local dir target
  dir="$(mktemp -d)"
  target="$dir/valid.json"

  printf '{"ok":true}\n' | atomic_write_json "$target"

  jq -e '.ok == true' "$target" >/dev/null || fail "target JSON is invalid"
  assert_mode_0600 "$target"
  rm -rf "$dir"
}

test_killed_writer_never_exposes_partial_target() {
  local dir target sentinel writer observed
  dir="$(mktemp -d)"
  target="$dir/sentinel.json"
  sentinel='{"sentinel":true}'

  printf '%s\n' "$sentinel" | atomic_write_json "$target"

  (
    printf '{'
    sleep 5
    printf '"sentinel":false}\n'
  ) | atomic_write_json "$target" &
  writer=$!

  for _ in $(seq 1 20); do
    observed="$(cat "$target")"
    [ "$observed" = "$sentinel" ] || fail "observed partial or replaced target: $observed"
    jq -e . "$target" >/dev/null || fail "observed invalid JSON in target"
    sleep 0.05
  done

  kill -9 "$writer" 2>/dev/null || true
  wait "$writer" 2>/dev/null || true

  observed="$(cat "$target")"
  [ "$observed" = "$sentinel" ] || fail "target changed after killed writer: $observed"
  jq -e . "$target" >/dev/null || fail "target invalid after killed writer"
  rm -rf "$dir"
}

test_rejects_invalid_json
test_writes_valid_json_with_private_mode
test_killed_writer_never_exposes_partial_target

echo "atomic_write_json tests passed"
