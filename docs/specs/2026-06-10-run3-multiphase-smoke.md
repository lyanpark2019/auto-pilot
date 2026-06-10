---
type: spec
topic: run3-multiphase-smoke
manual_edit: true
---

# Run 3 Multi-phase Smoke — 2-phase brownfield

**Date**: 2026-06-10
**Status**: live-run input (proves F-6 sync-dispatch fix + multi-phase advance in ONE run)
**Scope**: Two phases, one contract each, both EDIT existing test files. Run with the
F-6-fixed prompts (`99ec36f`): every subagent dispatch must be synchronous; the
session must not exit with subagents in flight.

## Why

Live run 2 proved the Step-2 bundle but stalled on F-6 (background reviewer
dispatch). This run must complete BOTH phases in-loop with the fixed prompts —
phase advance without orphaned subagents is the acceptance.

## Phase 1 — authorization key redaction test

**Goal**: single worker EDITS the existing `tests/test_log.py` (no new files) and
appends one test:

```python
def test_event_redacts_authorization_key(capsys) -> None:
    event("sample.auth", authorization="Basic dXNlcjpwYXNz", visible="yes")

    captured = capsys.readouterr()

    assert "authorization=<redacted>" in captured.err
    assert "dXNlcjpwYXNz" not in captured.err
    assert "visible=yes" in captured.err
```

**Scope files**: `tests/test_log.py` (existing — EDIT)

**Acceptance**:
- All pre-existing tests unchanged.
- New `test_event_redacts_authorization_key` present, asserts `_SECRET_KEY_RE`
  key-based redaction exactly as above.
- `python3 -m pytest -q tests/test_log.py` passes (4 tests).
- ruff clean on the file. Single commit with trailer block.

**Verify cmd**: `python3 -m pytest -q tests/test_log.py`

## Phase 2 — Freshness.to_json round-trip test

**Goal**: single worker EDITS the existing `tests/test_discovery.py` (no new
files) and appends one test:

```python
def test_freshness_to_json_shape():
    f = _discovery.Freshness(fresh=False, reason="scope-intersects", changed_files=("a.py",))
    assert f.to_json() == {"fresh": False, "reason": "scope-intersects", "changed_files": ["a.py"]}
```

**Scope files**: `tests/test_discovery.py` (existing — EDIT)

**Acceptance**:
- All pre-existing tests unchanged.
- New `test_freshness_to_json_shape` present (CLI output-shape invariant).
- `python3 -m pytest -q tests/test_discovery.py` passes.
- ruff clean on the file. Single commit with trailer block.

**Verify cmd**: `python3 -m pytest -q tests/test_discovery.py`

## Non-goals

- No changes outside the two scope files; no new files; no refactoring.
- Reviewers review normally.

## Cleanup

Both added tests are genuine invariant guards and STAY. Re-running requires
removing them first.
