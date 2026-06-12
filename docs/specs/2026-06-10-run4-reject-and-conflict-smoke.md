---
type: spec
topic: run4-reject-and-conflict-smoke
manual_edit: true
---

# Run 4 — REJECT round + merge-conflict smoke

**Date**: 2026-06-10
**Status**: live-run input (proves: reviewer REJECT→fix→APPROVE loop ·
multi-contract parallel · `apply_to_main` conflict path · the run-3 residual
exit/entry gates + headless guard live)
**Run with**: `/auto-pilot-server` headless, F-6-fixed prompts.

## Phase 1 — seeded-defect REJECT round (1 contract)

**Goal**: a worker EDITS the existing `tests/test_status.py` and appends ONE
test, but the round-1 worker ticket instructs committing WITHOUT the mandatory
trailer block. Spec acceptance REQUIRES the trailer block. Reviewers must catch
the missing trailers → REJECT → round-2 adds trailers → APPROVE → merge.

`tests/test_status.py` already does `import _status` at the top, so the appended
test references `_status.TERMINAL` directly (no new import):

```python
def test_worker_status_terminal_set_nonempty() -> None:
    assert len(_status.TERMINAL) >= 1
```

**Scope files**: `tests/test_status.py` (existing — EDIT)

**Acceptance**:
- Round 1 commit deliberately omits the trailer block (`Rejected:` /
  `Confidence:` etc.) → at least one reviewer REJECTs citing missing trailers.
- Round 2 re-commit includes the full trailer block → both reviewers APPROVE.
- `python3 -m pytest -q tests/test_status.py` passes.
- Phase advances ONLY after dual APPROVE — the phase-end evidence gate
  (`scripts/_evidence.py` `gate_phase_end`) must prove it.

**Expected gate behavior**: if reviewers MISS the missing trailers, that is a
recorded reviewer-quality P1 finding (both outcomes are signal). The phase-end
exit gate still blocks advance unless both `review.json` are APPROVE + sha-bound.

**Verify cmd**: `python3 -m pytest -q tests/test_status.py`

## Phase 2 — merge-conflict + multi-contract parallel (2 contracts)

**Goal**: two contracts dispatched in parallel, BOTH appending a test at the END
of the SAME file `tests/test_log.py` → guaranteed textual conflict in
`apply_to_main`.

`tests/test_log.py` already does `from scripts._log import event` at the top, so
the appended tests call `event(...)` directly (no new import).

Contract A appends:

```python
def test_log_event_emits_to_stderr_a(capsys) -> None:
    event("smoke.a", k="v")
    assert "smoke.a" in capsys.readouterr().err
```

Contract B appends:

```python
def test_log_event_emits_to_stderr_b(capsys) -> None:
    event("smoke.b", k="v")
    assert "smoke.b" in capsys.readouterr().err
```

**Scope files**: both contracts list `tests/test_log.py` (existing — EDIT).

**Acceptance**:
- One contract merges first; the second's `apply_to_main` returns a conflict
  result (`git am --abort`, main stays clean — assert `git status --porcelain`
  empty after the abort).
- PM re-dispatches the conflicted contract rebased on the new main → it merges.
- Both tests present and passing at phase end.
- A conflict event is logged; main is never left dirty.

**Verify cmd**: `python3 -m pytest -q tests/test_log.py`

## Non-goals

No changes outside the named scope files; no new files; no refactoring.
Reviewers review normally (phase-1's REJECT is driven by the seeded ticket
instruction, not by relaxing review).

## Cleanup

The added tests are genuine smoke guards and STAY. Re-running requires removing
them first. The seeded-defect instruction lives in the run's worker ticket, not
in the committed test.
