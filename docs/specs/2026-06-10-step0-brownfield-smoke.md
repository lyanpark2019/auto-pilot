---
type: spec
topic: step0-brownfield-smoke
manual_edit: true
---

# Step 0 Brownfield Smoke — 1-phase

**Date**: 2026-06-10
**Status**: live-run input (master-plan §5 Step 0.2 — first real e2e of the loop)
**Scope**: Single-phase, single-contract spec that EDITS one existing file. The
greenfield `2026-05-28-dogfood-smoke.md` creates new files; this spec proves the
brownfield path: worker must read existing code, modify it in place, and keep the
suite green.

## Why

The loop has never run live with real subagents (master-plan §4 honest gap). This
spec is the cheapest possible brownfield exercise: one worker, one existing-file
edit, deterministic verify, dual review, one commit.

## Phase 1 — Strengthen TERMINAL invariant test

**Goal**: PM dispatches a single worker. Worker edits the EXISTING file
`tests/test_status.py` (do not create any new file) and adds one test function
`test_terminal_is_all_but_partial` asserting the set-level invariant:

```python
def test_terminal_is_all_but_partial():
    assert _status.TERMINAL == frozenset(_status.WorkerStatus) - {_status.WorkerStatus.PARTIAL}
```

**Scope files**: `tests/test_status.py` (existing — EDIT, not create)

**Acceptance**:
- `tests/test_status.py` still contains the two pre-existing tests, unchanged.
- New function `test_terminal_is_all_but_partial` present and asserts
  `TERMINAL == frozenset(WorkerStatus) - {PARTIAL}` (exact set equality, not
  per-member checks).
- `python3 -m pytest -q tests/test_status.py` passes (3 tests).
- ruff clean on the file.
- Single commit, trailer block (`auto-pilot-iter`, `auto-pilot-phase: 1`).

**Verify cmd**: `python3 -m pytest -q tests/test_status.py`

## Non-goals

- No changes to `scripts/_status.py` or any other file.
- No new files anywhere.
- No refactoring of the existing two tests.
- One round of dual review should approve — the diff is ~3 lines.

## Cleanup

The added test is a genuine invariant guard and STAYS after the run. A re-run of
this spec requires removing the function first (the worker would otherwise no-op).
