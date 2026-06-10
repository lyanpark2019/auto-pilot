---
type: spec
topic: step2-bundle-smoke
manual_edit: true
---

# Step 2 Bundle Smoke — 2-phase brownfield

**Date**: 2026-06-10
**Status**: live-run input (proves Step-2 bundle wiring live + multi-phase advance)
**Scope**: Two phases, one contract each, both EDIT existing test files. Run with
graphify provenance recorded so the PM's dispatch step 0 resolves
`project-context.md` into every contract bundle.

## Why

Step 2 shipped the `resolve_report` seam and PM wiring, but no live worker has
received `project-context.md` in its bundle yet, and the loop has never advanced
past phase 1 live. This spec proves both at minimum cost.

## Phase 1 — gh token redaction test

**Goal**: single worker EDITS the existing `tests/test_log.py` (no new files) and
appends one test:

```python
def test_event_redacts_gh_token_values(capsys) -> None:
    event("sample.gh", note="ghp_abcdefghijklmnop", plain="ok")

    captured = capsys.readouterr()

    assert "note=<redacted>" in captured.err
    assert "ghp_abcdefghijklmnop" not in captured.err
    assert "plain=ok" in captured.err
```

**Scope files**: `tests/test_log.py` (existing — EDIT)

**Acceptance**:
- Both pre-existing tests unchanged.
- New `test_event_redacts_gh_token_values` present, asserts gh-token redaction
  via `_SECRET_VALUE_RE` behavior exactly as above.
- `python3 -m pytest -q tests/test_log.py` passes (3 tests).
- ruff clean on the file. Single commit with trailer block.

**Verify cmd**: `python3 -m pytest -q tests/test_log.py`

## Phase 2 — WorkerStatus str-coercion test

**Goal**: single worker EDITS the existing `tests/test_status.py` (no new files)
and appends one test:

```python
def test_worker_status_is_str():
    assert isinstance(_status.WorkerStatus.DONE, str)
    assert f"{_status.WorkerStatus.DONE.value}" == "DONE"
```

**Scope files**: `tests/test_status.py` (existing — EDIT)

**Acceptance**:
- All pre-existing tests unchanged.
- New `test_worker_status_is_str` present (str-subclass invariant of the enum).
- `python3 -m pytest -q tests/test_status.py` passes (4 tests).
- ruff clean on the file. Single commit with trailer block.

**Verify cmd**: `python3 -m pytest -q tests/test_status.py`

## Non-goals

- No changes outside the two scope files; no new files; no refactoring.
- Reviewers review normally — no special instructions.

## Cleanup

Both added tests are genuine invariant guards and STAY. Re-running this spec
requires removing them first (workers would otherwise no-op).
