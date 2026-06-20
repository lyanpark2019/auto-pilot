#!/usr/bin/env bash
# Compute a STABLE run_id for the reviewed work unit and export it as RUN_ID.
#
# WHY: the learning-loop miner derives distinct_runs from the per-line run_id
# (auto-pilot scripts/_improvement.py:314, learning_miner.py:162-167). Archon's
# $WORKFLOW_ID is a per-run TEXT substitution (packages/workflows/src/
# executor-shared.ts:441) that changes every execution, so using it as run_id
# inflates distinct_runs on same-diff re-runs. run_id must instead derive from
# the reviewed work unit: the committed tree (git rev-parse HEAD) when clean,
# else the hash of the diff under review ($ARTIFACTS_DIR/diff.patch).
#
# Output: prints the run_id to stdout and (when sourced) exports RUN_ID.
# Guarantee: RUN_ID is never equal to $WORKFLOW_ID.

set -euo pipefail

compute_run_id() {
    local artifacts_dir patch_file head_sha sum_out
    artifacts_dir="${ARTIFACTS_DIR:-.}"
    patch_file="${artifacts_dir%/}/diff.patch"

    # Clean tree -> bind to the committed work unit.
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
        && [ -z "$(git status --porcelain 2>/dev/null)" ]; then
        if head_sha="$(git rev-parse HEAD 2>/dev/null)" && [ -n "$head_sha" ]; then
            printf '%s\n' "$head_sha"
            return 0
        fi
    fi

    # Dirty tree (or no commit) -> bind to the hash of the diff under review.
    if [ -f "$patch_file" ]; then
        sum_out="$(shasum "$patch_file")"
        # First whitespace-delimited field is the hash.
        printf '%s\n' "${sum_out%% *}"
        return 0
    fi

    echo "run_id_from_diff: no clean HEAD and no $patch_file to hash" >&2
    return 1
}

main() {
    local run_id
    run_id="$(compute_run_id)"

    # Invariant: run_id must never collide with the per-run $WORKFLOW_ID text.
    if [ -n "${WORKFLOW_ID:-}" ] && [ "$run_id" = "$WORKFLOW_ID" ]; then
        run_id="${run_id}-diff"
    fi

    export RUN_ID="$run_id"
    printf '%s\n' "$RUN_ID"
}

main "$@"
