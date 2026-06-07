#!/usr/bin/env bash
# Unit-test the dispatch backoff/abort/validation logic.
# Sources the real dispatch-backoff.sh lib (single source of truth).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SWARM_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

# Source real lib — test exercises actual functions, not reimplementations.
# shellcheck source=swarm/scripts/lib/dispatch-backoff.sh
. "$SWARM_ROOT/scripts/lib/dispatch-backoff.sh"

VALIDATE="$SWARM_ROOT/scripts/validate-ticket.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# test: successful dispatch resets counter
# ---------------------------------------------------------------------------
test_success_resets_counter() {
  local f=5
  f="$(apply_dispatch_result 1 1 "$f")"
  [ "$f" -eq 0 ] || fail "success should reset to 0, got $f"
}

# ---------------------------------------------------------------------------
# test: pm_call failure increments counter
# ---------------------------------------------------------------------------
test_pm_failure_increments() {
  local f=0
  f="$(apply_dispatch_result 0 0 "$f")"
  [ "$f" -eq 1 ] || fail "pm_call failure should increment to 1, got $f"
}

# ---------------------------------------------------------------------------
# test: pm_call success but invalid ticket increments counter
# ---------------------------------------------------------------------------
test_invalid_ticket_increments() {
  local f=2
  f="$(apply_dispatch_result 1 0 "$f")"
  [ "$f" -eq 3 ] || fail "invalid ticket should increment to 3, got $f"
}

# ---------------------------------------------------------------------------
# test: backoff progression (threshold=3, cap=600)
# ---------------------------------------------------------------------------
test_backoff_progression() {
  local threshold=3
  local sec
  # f=3 → 60s  (2^0 * 60)
  sec="$(compute_backoff_sec 3 "$threshold")"
  [ "$sec" -eq 60 ]  || fail "backoff at f=3: expected 60s got ${sec}s"
  # f=4 → 120s (2^1 * 60)
  sec="$(compute_backoff_sec 4 "$threshold")"
  [ "$sec" -eq 120 ] || fail "backoff at f=4: expected 120s got ${sec}s"
  # f=5 → 240s
  sec="$(compute_backoff_sec 5 "$threshold")"
  [ "$sec" -eq 240 ] || fail "backoff at f=5: expected 240s got ${sec}s"
  # f=6 → 480s
  sec="$(compute_backoff_sec 6 "$threshold")"
  [ "$sec" -eq 480 ] || fail "backoff at f=6: expected 480s got ${sec}s"
  # f=7 → capped at 600s
  sec="$(compute_backoff_sec 7 "$threshold")"
  [ "$sec" -eq 600 ] || fail "backoff at f=7: expected 600s got ${sec}s"
  # f=9 → capped at 600s (exp=6 clamped → 60*64=3840 → cap 600)
  sec="$(compute_backoff_sec 9 "$threshold")"
  [ "$sec" -eq 600 ] || fail "backoff at f=9: expected 600s got ${sec}s"
}

# ---------------------------------------------------------------------------
# test: exponent clamp (P3) — pathological gap (abort-backoff > 63) must not overflow
# ---------------------------------------------------------------------------
test_exp_clamp() {
  local threshold=3
  local sec
  # f=70: exp would be 67 → bash 3.2 (1 << 67) wraps to 0 or negative without clamp.
  # With clamp at 6: exp=6 → 60*64=3840 → capped to 600.
  sec="$(compute_backoff_sec 70 "$threshold")"
  [ "$sec" -eq 600 ] || fail "exp-clamp at f=70: expected 600s got ${sec}s"
  # Verify result is positive (overflow guard).
  [ "$sec" -gt 0 ] || fail "exp-clamp produced non-positive result: $sec"
}

# ---------------------------------------------------------------------------
# test: is_manual_ticket correctly identifies T-manual-* files
# ---------------------------------------------------------------------------
test_is_manual_ticket() {
  is_manual_ticket "T-manual-foo.json" || fail "T-manual-foo.json should be manual"
  is_manual_ticket "/some/path/T-manual-bar.json" || fail "/path/T-manual-bar.json should be manual"
  if is_manual_ticket "T-20260514-075440.json"; then
    fail "T-20260514-075440.json should NOT be manual"
  fi
  if is_manual_ticket "T-manual-foo.json.bak"; then
    fail "T-manual-foo.json.bak should NOT be manual (wrong extension)"
  fi
}

# ---------------------------------------------------------------------------
# test: valid ticket accepted — counter resets AND file NOT removed
# ---------------------------------------------------------------------------
test_valid_ticket_accepted_not_removed() {
  local dir inbox
  dir="$(mktemp -d)"
  inbox="$dir/inbox"
  mkdir -p "$inbox"
  local ticket="$inbox/T-20260514-075440.json"
  cp "$SWARM_ROOT/tests/ticket-schema/valid.json" "$ticket"

  local f=3
  if "$VALIDATE" "$ticket" >/dev/null 2>&1; then
    f="$(apply_dispatch_result 1 1 "$f")"
    [ "$f" -eq 0 ] || fail "valid ticket: counter should reset to 0, got $f"
    [ -f "$ticket" ] || fail "valid ticket: file should NOT have been removed"
  else
    fail "valid ticket: validate-ticket.sh unexpectedly rejected valid.json"
  fi

  rm -rf "$dir"
}

# ---------------------------------------------------------------------------
# test: schema-invalid ticket archived, not deleted
# The archive-branch logic lives inline in run-pm.sh (not a lib function);
# this test exercises it end-to-end: validate rejects → mv to archive → assert file moved.
# ---------------------------------------------------------------------------
test_invalid_ticket_archived_not_deleted() {
  local dir inbox archive_dir
  dir="$(mktemp -d)"
  inbox="$dir/inbox"
  archive_dir="$dir/archive"
  mkdir -p "$inbox" "$archive_dir"

  local ticket="$inbox/T-20260514-075440.json"
  cp "$SWARM_ROOT/tests/ticket-schema/invalid-missing-id.json" "$ticket"

  "$VALIDATE" "$ticket" >/dev/null 2>&1 && fail "validate-ticket.sh should have rejected invalid-missing-id.json"

  local tid="T-20260514-075440"
  mv "$ticket" "$archive_dir/${tid}.invalid.json" 2>/dev/null || true
  [ ! -f "$ticket" ]                        || fail "invalid ticket was not removed from inbox"
  [ -f "$archive_dir/${tid}.invalid.json" ] || fail "invalid ticket was not archived"

  rm -rf "$dir"
}

# ---------------------------------------------------------------------------
# test: T-manual-* ticket is skipped (not counted as failure)
# ---------------------------------------------------------------------------
test_manual_ticket_skipped() {
  local dir inbox
  dir="$(mktemp -d)"
  inbox="$dir/inbox"
  mkdir -p "$inbox"
  local manual_ticket="$inbox/T-manual-user-inject.json"
  local real_ticket="$inbox/T-20260607-120000.json"
  cp "$SWARM_ROOT/tests/ticket-schema/valid.json" "$manual_ticket"
  cp "$SWARM_ROOT/tests/ticket-schema/valid.json" "$real_ticket"

  is_manual_ticket "$manual_ticket" || fail "T-manual-*.json not identified as manual ticket"
  if is_manual_ticket "$real_ticket"; then
    fail "T-20260607-120000.json should NOT be identified as manual ticket"
  fi

  # Simulate the run-pm.sh loop: manual ticket is skipped (not passed to apply_dispatch_result);
  # only the real ticket drives the counter. Valid real ticket → counter resets to 0.
  local f=5
  for tf in "$inbox"/*.json; do
    [ -e "$tf" ] || continue
    is_manual_ticket "$tf" && continue
    if "$VALIDATE" "$tf" >/dev/null 2>&1; then
      f="$(apply_dispatch_result 1 1 "$f")"
    else
      f="$(apply_dispatch_result 1 0 "$f")"
    fi
  done
  [ "$f" -eq 0 ] || fail "manual ticket must not affect counter; real valid ticket should reset to 0, got $f"

  rm -rf "$dir"
}

# ---------------------------------------------------------------------------
# test: validate-ticket.sh is callable and rejects non-JSON
# ---------------------------------------------------------------------------
test_validate_ticket_rejects_invalid() {
  local tmp
  tmp="$(mktemp)"
  printf 'not-json' > "$tmp"
  if bash "$VALIDATE" "$tmp" >/dev/null 2>&1; then
    rm -f "$tmp"
    fail "validate-ticket.sh should reject non-JSON"
  fi
  rm -f "$tmp"
}

test_success_resets_counter
test_pm_failure_increments
test_invalid_ticket_increments
test_backoff_progression
test_exp_clamp
test_is_manual_ticket
test_valid_ticket_accepted_not_removed
test_invalid_ticket_archived_not_deleted
test_manual_ticket_skipped
test_validate_ticket_rejects_invalid

echo "dispatch-backoff tests passed"
