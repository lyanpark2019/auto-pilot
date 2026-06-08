# v0.8.7 Logging Output Contract

## Scope
- Owned files:
  - `vault/scripts/lockfile.py`
  - `vault/pipeline/scan_code.py`
  - `vault/scripts/selftest.py`
  - `vault/scripts/score_content.py`
  - `vault/scripts/score_structural.py`
  - `vault/pipeline/loop.py`
- Forbidden files:
  - hook decision behavior
  - release manifests
  - `.planning/quality/score-state.json` before final rescore

## Target metrics
- before:
  - raw print calls: 168
  - event text hits: 37
  - error_type text hits: 10
- after:
  - Wave 1: raw print calls <=110
  - Wave 2: raw print calls <=80
  - error paths include `error_type=` where meaningful

## Required tests
- RED/characterization:
  - CLI stdout/stderr contract snapshots for changed scripts when existing tests do not cover output.
- GREEN:
  - `( cd vault && python3 -m pytest tests/test_lockfile.py tests/test_selftest.py tests/test_score_structural.py -q )`
  - `python3 scripts/quality/metric_snapshot.py`
  - `python3 -m ruff check vault/ scripts/ hooks/ tests/`

## Deliverable
- commit(s): pending
- metric delta: raw print calls 168 -> 97 after converting vault loop/scoring/cost/selftest/self-improve/migration outputs to stream helpers
- residual risk: 97 raw prints remain, led by `scripts/orchestrator.py`, asset/doc check scripts, hook selftest scripts, and several vault restructure/dispatch utilities.
