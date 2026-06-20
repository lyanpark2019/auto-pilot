#!/usr/bin/env bash
# Test for run_id_from_diff.sh:
#   (a) same committed diff, run twice -> identical RUN_ID (clean-tree git branch)
#   (b) one-byte mutation of a fake diff.patch -> different RUN_ID (dirty fallback)
#   (c) RUN_ID != a sample $WORKFLOW_ID value

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$SCRIPT_DIR/run_id_from_diff.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() {
    echo "FAIL: $1" >&2
    exit 1
}

# --- (a) clean committed tree: two runs -> identical RUN_ID -------------------
REPO="$TMP/repo"
mkdir -p "$REPO"
(
    cd "$REPO" || exit 1
    git init -q -b main
    git config user.email t@t.t
    git config user.name t
    printf 'a\n' >file.txt
    git add file.txt
    git commit -qm init
)

RUN_A1="$(cd "$REPO" && ARTIFACTS_DIR="$REPO" bash "$HELPER")"
RUN_A2="$(cd "$REPO" && ARTIFACTS_DIR="$REPO" bash "$HELPER")"

[ -n "$RUN_A1" ] || fail "(a) empty RUN_ID"
[ "$RUN_A1" = "$RUN_A2" ] || fail "(a) clean-tree run_id not stable: $RUN_A1 != $RUN_A2"

EXPECTED_HEAD="$(cd "$REPO" && git rev-parse HEAD)"
[ "$RUN_A1" = "$EXPECTED_HEAD" ] || fail "(a) run_id not the committed HEAD: $RUN_A1 != $EXPECTED_HEAD"
echo "PASS (a) clean committed tree -> stable run_id = HEAD ($RUN_A1)"

# --- (b) dirty tree, one-byte mutation of diff.patch -> different RUN_ID ------
# Use a non-git dir so the clean-tree branch is skipped and the shasum fallback runs.
ART="$TMP/artifacts"
mkdir -p "$ART"
printf 'diff --git a/x b/x\n+aaaa\n' >"$ART/diff.patch"
RUN_B1="$(ARTIFACTS_DIR="$ART" bash "$HELPER")"

# Mutate exactly one byte.
printf 'diff --git a/x b/x\n+aaab\n' >"$ART/diff.patch"
RUN_B2="$(ARTIFACTS_DIR="$ART" bash "$HELPER")"

[ -n "$RUN_B1" ] || fail "(b) empty RUN_ID before mutation"
[ -n "$RUN_B2" ] || fail "(b) empty RUN_ID after mutation"
[ "$RUN_B1" != "$RUN_B2" ] || fail "(b) one-byte mutation did not change run_id: $RUN_B1"

# Stability sanity: same bytes -> same hash.
printf 'diff --git a/x b/x\n+aaaa\n' >"$ART/diff.patch"
RUN_B3="$(ARTIFACTS_DIR="$ART" bash "$HELPER")"
[ "$RUN_B1" = "$RUN_B3" ] || fail "(b) diff-hash not stable: $RUN_B1 != $RUN_B3"
echo "PASS (b) diff.patch one-byte mutation -> different run_id ($RUN_B1 -> $RUN_B2)"

# --- (c) RUN_ID != sample $WORKFLOW_ID ---------------------------------------
SAMPLE_WF="wf-20260620-abc123"

# Clean-tree path under a WORKFLOW_ID that differs from HEAD.
RUN_C1="$(cd "$REPO" && WORKFLOW_ID="$SAMPLE_WF" ARTIFACTS_DIR="$REPO" bash "$HELPER")"
[ "$RUN_C1" != "$SAMPLE_WF" ] || fail "(c) run_id equals WORKFLOW_ID (clean): $RUN_C1"

# Force the pathological collision: set WORKFLOW_ID == the value the helper would
# otherwise emit, and assert it is disambiguated (never equal).
RUN_C2="$(cd "$REPO" && WORKFLOW_ID="$EXPECTED_HEAD" ARTIFACTS_DIR="$REPO" bash "$HELPER")"
[ "$RUN_C2" != "$EXPECTED_HEAD" ] || fail "(c) run_id collided with WORKFLOW_ID after override: $RUN_C2"
echo "PASS (c) run_id != WORKFLOW_ID (incl. forced-collision case: $RUN_C2)"

echo "ALL TESTS PASSED"
