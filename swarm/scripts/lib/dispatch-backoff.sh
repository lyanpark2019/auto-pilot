#!/usr/bin/env bash
# Dispatch counter + backoff logic — sourced by run-pm.sh and tests.
# Functions write results to stdout; callers capture with $(...).

# apply_dispatch_result <dispatch_ok 0|1> <ticket_valid 0|1> <current_failures>
# Prints new DISPATCH_FAILURES value.
apply_dispatch_result() {
  local ok="$1" valid="$2" failures="$3"
  if [ "$ok" -eq 1 ] && [ "$valid" -eq 1 ]; then
    echo 0
  else
    echo "$((failures + 1))"
  fi
}

# compute_backoff_sec <failures> <backoff_threshold>
# Prints capped exponential backoff seconds (max 600).
# Exponent is clamped to 6 to prevent shift-overflow on bash 3.2 with large gaps.
compute_backoff_sec() {
  local failures="$1" threshold="$2"
  local local_exp backoff_sec
  local_exp=$((failures - threshold))
  if [ "$local_exp" -gt 6 ]; then local_exp=6; fi
  backoff_sec=$((60 * (1 << local_exp)))
  if [ "$backoff_sec" -gt 600 ]; then backoff_sec=600; fi
  echo "$backoff_sec"
}

# is_manual_ticket <filename>
# Returns 0 (true) if the basename matches T-manual-*.json
is_manual_ticket() {
  local base
  base="$(basename "$1")"
  case "$base" in
    T-manual-*.json) return 0;;
    *) return 1;;
  esac
}
