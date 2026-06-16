#!/usr/bin/env bash
# Guard tests for start.sh: core-loop conflict detection.
# (a) running state → exit 3 + message on stderr
# (b) absent state file → no false block (start.sh exits at config-required check,
#     not the guard — confirms guard did not trigger)
# (c) terminal status (stopped/failed/success) → no block
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SWARM_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
START_SH="$SWARM_ROOT/scripts/start.sh"

# start.sh sources $CLAUDE_PLUGIN_ROOT/swarm/scripts/lib/swarm-models.sh; point it
# at this repo so the source resolves on a clean CI runner (no installed plugin).
# The running-state guard runs BEFORE that source, so case (a) does not depend on it.
CLAUDE_PLUGIN_ROOT="$(cd -- "$SWARM_ROOT/.." && pwd)"
export CLAUDE_PLUGIN_ROOT

fail() { echo "FAIL: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# helper: run start.sh inside a temporary project dir that has no config
# so it exits at the config-required check (exit 2), not later.
# We intercept at exit 3 (guard) vs exit 2 (config missing) to distinguish.
# ---------------------------------------------------------------------------
run_start_in_tmp() {
  local project_dir="$1"
  local rc=0
  bash "$START_SH" --no-attach 2>"$project_dir/err.txt" || rc=$?
  echo "$rc"
}

# ---------------------------------------------------------------------------
# (a) running state → guard fires, exit 3, stderr message present
# ---------------------------------------------------------------------------
test_running_state_blocks() {
  local dir
  dir="$(mktemp -d)"

  mkdir -p "$dir/.planning/auto-pilot"
  printf '{"status": "running"}' > "$dir/.planning/auto-pilot/state.json"

  local rc
  rc="$(cd "$dir" && run_start_in_tmp "$dir")"

  [ "$rc" -eq 3 ] || fail "running state: expected exit 3, got $rc"
  grep -q "refusing to start" "$dir/err.txt" || fail "running state: expected 'refusing to start' on stderr"
  grep -q "status=running" "$dir/err.txt" || fail "running state: expected 'status=running' on stderr"

  rm -rf "$dir"
}

# ---------------------------------------------------------------------------
# (b) absent state file → guard does NOT fire; start.sh exits 2 (config missing)
# ---------------------------------------------------------------------------
test_absent_state_no_block() {
  local dir
  dir="$(mktemp -d)"

  # No .planning/auto-pilot/ directory at all.
  local rc
  rc="$(cd "$dir" && run_start_in_tmp "$dir")"

  # Guard must NOT fire: no exit 3 and no guard message on stderr. We assert on
  # the guard's observable effect, not the incidental post-guard exit code.
  [ "$rc" -ne 3 ] || fail "absent state: guard fired falsely (exit 3)"
  ! grep -q "refusing to start" "$dir/err.txt" || fail "absent state: guard message emitted falsely"

  rm -rf "$dir"
}

# ---------------------------------------------------------------------------
# (c) terminal status (stopped / failed / success / pivot-needed) → no block
# ---------------------------------------------------------------------------
test_terminal_status_no_block() {
  local dir status
  for status in stopped failed success pivot-needed; do
    dir="$(mktemp -d)"

    mkdir -p "$dir/.planning/auto-pilot"
    printf '{"status": "%s"}' "$status" > "$dir/.planning/auto-pilot/state.json"

    local rc
    rc="$(cd "$dir" && run_start_in_tmp "$dir")"

    [ "$rc" -ne 3 ] || fail "terminal status '$status': guard fired falsely (exit 3)"
    ! grep -q "refusing to start" "$dir/err.txt" || fail "terminal status '$status': guard message emitted falsely"

    rm -rf "$dir"
  done
}

test_running_state_blocks
test_absent_state_no_block
test_terminal_status_no_block

echo "tests/start PASS"
