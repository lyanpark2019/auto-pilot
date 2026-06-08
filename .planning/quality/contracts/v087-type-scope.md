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

## Required tests
- RED/characterization:
  - `python3 -m pytest tests/test_mypy_scope.py -q` fails after adding expected files but before `mypy.ini` update.
  - single-file mypy measurements recorded for each candidate.
- GREEN:
  - `python3 -m pytest tests/test_mypy_scope.py -q`
  - `python3 -m mypy`

## Deliverable
- commit(s): pending
- metric delta: pending
- residual risk: skip any candidate with broad architectural type debt instead of forcing it into strict scope.
