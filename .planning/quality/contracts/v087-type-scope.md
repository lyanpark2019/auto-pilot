# v0.8.7 Type Scope Contract

## Scope
- Owned files:
  - `mypy.ini`
  - `tests/test_mypy_scope.py`
  - `vault/sources/_adapter.py`
  - `vault/sources/docs.py`
  - `vault/pipeline/scan_code.py`
  - `vault/scripts/lockfile.py`
  - `vault/scripts/dashboard_data.py`
  - `vault/pipeline/drift.py`
- Forbidden files:
  - release manifests
  - hook behavior files except via PM handoff
  - `.planning/quality/score-state.json` before final rescore

## Target metrics
- before:
  - strict vault mypy pilots: 2
  - mypy source files: 36
- after:
  - strict vault mypy pilots: >=8
  - full `python3 -m mypy` clean
  - Wave 3: strict vault mypy pilots >=11

## Required tests
- RED/characterization:
  - `python3 -m pytest tests/test_mypy_scope.py -q` fails after adding expected files but before `mypy.ini` update.
  - single-file mypy measurements recorded for each candidate.
- GREEN:
  - `python3 -m pytest tests/test_mypy_scope.py -q`
  - `python3 -m mypy`

## Candidate measurement
- accepted: `vault/sources/_excludes.py` (clean), `vault/pipeline/bases.py` (clean), `vault/pipeline/scan_code.py` (clean), `vault/pipeline/state.py` (1 local fix), `vault/pipeline/scan_docs.py` (1 local fix), `vault/scripts/lockfile.py` (1 local fix)
- skipped: `vault/sources/docs.py` (file absent), `vault/pipeline/drift.py` (14 errors), `vault/sources/_adapter.py` (3 errors), `vault/scripts/dashboard_data.py` (4 errors)

## Deliverable
- commit(s): pending
- metric delta: strict vault mypy pilots 2 -> 11; mypy source files 37 -> 46 after Task 1 scanner, Wave 1 type scope, and Wave 3 dispatch/loop/self_improve expansion
- residual risk: broader vault strict scope remains staged; skipped candidates such as full drift/source adapter typing require separate focused work.
