#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# test-no-overlap.sh
# Assert that no two live tickets on the autopilot bus share a scope_paths
# entry.  Locks M2 success_criteria (grep -qi 'overlap\|scope_paths'
# scripts/run-pm.sh) from the verification side.
#
# Exit codes:
#   0  — no overlaps (or self-test passed)
#   1  — at least one scope_paths collision found
#   2  — self-test failed (detection logic broken)
#
# Env:
#   OVERLAP_SELFTEST=1  — run self-test mode instead of live-bus scan
# ---------------------------------------------------------------------------

REPO_ROOT="$(git rev-parse --show-toplevel)"
BUS_ROOT="${REPO_ROOT}/.planning/autopilot"

# emit_pairs DIR
# Print "<ticket_id>\t<scope_path>" for every JSON ticket under DIR.
# Skips non-existent dirs silently.
# Warns on malformed JSON; does NOT abort.
emit_pairs() {
  local dir="$1"
  [[ -d "${dir}" ]] || return 0

  local f raw_id ticket_id p
  while IFS= read -r f; do
    if ! jq -e . "${f}" >/dev/null 2>&1; then
      echo "WARN: skipping malformed JSON: ${f}" >&2
      continue
    fi
    raw_id="$(jq -r '.id // empty' "${f}" 2>/dev/null || true)"
    ticket_id="${raw_id:-$(basename "${f}" .json)}"
    while IFS= read -r p; do
      [[ -z "${p}" ]] && continue
      printf '%s\t%s\n' "${ticket_id}" "${p}"
    done < <(jq -r '.scope_paths[]? // empty' "${f}" 2>/dev/null || true)
  done < <(find "${dir}" -type f -name '*.json' 2>/dev/null | sort)
}

# detect_overlaps PAIRS_FILE
# Reads sorted <id>\t<path> pairs, prints "<path> claimed by <id1>, <id2>"
# for every path claimed by >=2 distinct ticket IDs.  Exit 0 always.
detect_overlaps() {
  local pf="$1"
  awk -F'\t' '
    function flush_group() {
      if (overlap) print prev_path " claimed by " ids
    }
    {
      if ($2 != prev_path) {
        flush_group()
        prev_path=$2; first_id=$1; ids=$1; overlap=0
      } else if ($1 != first_id) {
        ids = ids ", " $1; overlap=1
      }
    }
    END { flush_group() }
  ' "${pf}"
}

# ---------------------------------------------------------------------------
# SELF-TEST MODE
# Seed two fake tickets sharing a path; assert detection fires.
# ---------------------------------------------------------------------------
if [[ "${OVERLAP_SELFTEST:-0}" == "1" ]]; then
  SELFTEST_DIR="$(mktemp -d)"
  trap 'rm -rf "${SELFTEST_DIR}"' EXIT

  cat > "${SELFTEST_DIR}/T-ST-001.json" <<'TICKET_EOF'
{"id":"T-ST-001","scope_paths":["scripts/run-pm.sh","scripts/run-worker.sh"]}
TICKET_EOF

  cat > "${SELFTEST_DIR}/T-ST-002.json" <<'TICKET_EOF'
{"id":"T-ST-002","scope_paths":["scripts/run-pm.sh","README.md"]}
TICKET_EOF

  SELFTEST_PAIRS="$(mktemp)"
  trap 'rm -f "${SELFTEST_PAIRS}"' EXIT
  emit_pairs "${SELFTEST_DIR}" | sort -t$'\t' -k2,2 -k1,1 -u > "${SELFTEST_PAIRS}"

  DETECTED="$(detect_overlaps "${SELFTEST_PAIRS}")"

  if [[ -n "${DETECTED}" ]]; then
    echo "SELFTEST PASSED: overlap correctly detected" >&2
    echo "  → ${DETECTED}" >&2
    exit 0
  else
    echo "SELFTEST FAILED: overlap NOT detected (logic broken)" >&2
    exit 2
  fi
fi

# ---------------------------------------------------------------------------
# MAIN — scan live bus
# Scanned dirs:  .planning/autopilot/inbox/  (all worker-*/ subdirs)
#                .planning/autopilot/in_progress/
# Skipped:       archive/  done/  outbox/
# ---------------------------------------------------------------------------

PAIRS_FILE="$(mktemp)"
trap 'rm -f "${PAIRS_FILE}"' EXIT

{
  emit_pairs "${BUS_ROOT}/inbox"
  emit_pairs "${BUS_ROOT}/in_progress"
} | sort -t$'\t' -k2,2 -k1,1 -u > "${PAIRS_FILE}"

# Count unique ticket IDs
TOTAL_TICKETS="$(awk -F'\t' '{ids[$1]=1} END{n=0; for(k in ids) n++; print n}' "${PAIRS_FILE}")"
TOTAL_PATHS="$(wc -l < "${PAIRS_FILE}" | tr -d ' \t')"

# Edge cases: 0 or 1 ticket can never overlap
if [[ "${TOTAL_TICKETS}" -le 1 ]]; then
  echo "ok: ${TOTAL_TICKETS} tickets, ${TOTAL_PATHS} scope_paths, 0 overlaps"
  exit 0
fi

# Detect and report overlaps
OVERLAP_LINES="$(detect_overlaps "${PAIRS_FILE}")"

if [[ -n "${OVERLAP_LINES}" ]]; then
  while IFS= read -r line; do
    echo "OVERLAP: ${line}" >&2
  done <<< "${OVERLAP_LINES}"
  exit 1
fi

echo "ok: ${TOTAL_TICKETS} tickets, ${TOTAL_PATHS} scope_paths, 0 overlaps"
exit 0
