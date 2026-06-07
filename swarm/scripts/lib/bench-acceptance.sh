#!/usr/bin/env bash
# Bench acceptance helpers — sourced by bench.sh and bench-acceptance/test.sh.
# Single source of truth for the default acceptance command and accumulation logic.
# bench.sh accumulates --acceptance values by calling acceptance_append directly.

# Locale-free plumbing: exits 0 only if HEAD touched at least one file.
# Runs in the worker worktree (pm-score.md: cd <worktree> && <cmd>).
# Note: diff-tree without -m does not follow merge commits; on merge-only
# HEAD this returns no files (conservative false-reject).
BENCH_DEFAULT_ACCEPTANCE='git diff-tree --no-commit-id --name-only -r HEAD | grep -q .'

# acceptance_append <json_array_so_far> <value>
# Appends <value> to the JSON array and prints the new array to stdout.
# Fatal (exit 1) if value is empty, whitespace-only, or contains a newline or tab.
acceptance_append() {
  local acc="$1"
  local val="$2"
  case "$val" in
    '') printf 'bench: --acceptance value is empty\n' >&2; return 1;;
    *[^[:space:]]*) : ;;
    *) printf 'bench: --acceptance value is empty or whitespace-only\n' >&2; return 1;;
  esac
  case "$val" in
    *'
'*|*'	'*) printf 'bench: --acceptance value contains a newline or tab\n' >&2; return 1;;
  esac
  local quoted
  quoted="$(printf '%s' "$val" | jq -Rs .)"
  printf '%s' "$acc" | jq --argjson c "$quoted" '. + [$c]'
}

# build_acceptance_json <raw_args...>
# Reads --acceptance values from "$@" (already-stripped; caller passes only the
# values collected during option parsing).  Values are passed as positional args,
# one per --acceptance occurrence.  Prints a JSON array string to stdout.
# Exits non-zero and prints to stderr on empty/whitespace-only or newline/tab value.
#
# Usage: acceptance_json="$(build_acceptance_json "$val1" "$val2" ...)"
#   or   acceptance_json="$(build_acceptance_json)"  # zero args → default
build_acceptance_json() {
  if [ "$#" -eq 0 ]; then
    local def_quoted
    def_quoted="$(printf '%s' "$BENCH_DEFAULT_ACCEPTANCE" | jq -Rs .)"
    printf '[%s]' "$def_quoted"
    return 0
  fi
  local acc
  acc='[]'
  local val
  for val in "$@"; do
    acc="$(acceptance_append "$acc" "$val")" || return 1
  done
  printf '%s' "$acc"
}
