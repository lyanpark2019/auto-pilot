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

  # Guard exit = 3; config-missing exit = 2. We must NOT see 3.
  [ "$rc" -ne 3 ] || fail "absent state: guard fired falsely (exit 3)"
  # Confirm it stopped at the expected config-missing checkpoint.
  [ "$rc" -eq 2 ] || fail "absent state: expected exit 2 (config missing), got $rc"

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
    # Stopped at config-missing (exit 2), not the guard.
    [ "$rc" -eq 2 ] || fail "terminal status '$status': expected exit 2, got $rc"

    rm -rf "$dir"
  done
}

test_running_state_blocks
test_absent_state_no_block
test_terminal_status_no_block

echo "tests/start PASS"
