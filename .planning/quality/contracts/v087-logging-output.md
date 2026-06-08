# v0.8.7 Logging Output Contract

## Scope
- Owned files:
  - `vault/scripts/lockfile.py`
  - `vault/pipeline/scan_code.py`
  - `vault/scripts/selftest.py`
  - `vault/scripts/score_content.py`
  - `vault/scripts/score_structural.py`
  - `vault/pipeline/loop.py`
  - `scripts/_log.py`
  - `tests/test_log.py`
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
- metric delta: raw print calls 168 -> 0, event() calls 37 -> 59, long functions=0, broad exceptions=0, subprocess_without_timeout=0, shell_true_calls=0 after normalizing metric scope to production files, converting vault loop/scoring/cost/selftest/self-improve/migration/dashboard/dispatch/drift/MCP/doc/risk/worker outputs to stream helpers, adding secret-like key/value redaction to `event()`, adding `duration_ms` external-call events for risk/dispatch git subprocesses, and adding structured event logs to asset registry, eval runner/CLI, and graphify query loop
- residual risk: production stream writes preserve CLI stdout/stderr contracts but are still not all structured `event()` records because some tools intentionally emit JSON or user-facing reports.
