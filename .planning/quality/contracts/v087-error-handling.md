# v0.8.7 Error Handling Contract

## Scope
- Owned files:
  - `vault/scripts/lockfile.py`
  - `vault/tests/test_lockfile.py`
  - `vault/pipeline/scan_code.py`
  - `vault/tests/test_scan_code.py`
  - `hooks/codex-conductor-guard.py`
  - `hooks/test_codex_conductor_guard.py`
  - `scripts/graphify_vault_loop.py`
  - `tests/test_graphify_vault_loop.py`
- Forbidden files:
  - release manifests
  - unrelated CLI output rewrites owned by Logging Worker
  - structure-only refactors owned by Structure Worker unless PM reassigns

## Target metrics
- before:
  - broad exceptions: 30
- after:
  - Wave 1: <=20
  - Wave 2: <=15

## Required tests
- RED/characterization:
  - unexpected parser/runtime errors are not swallowed.
  - intentional recoverable paths include `error_type=` context.
- GREEN:
  - `( cd vault && python3 -m pytest tests/test_lockfile.py tests/test_scan_code.py -q )`
  - `python3 hooks/test_codex_conductor_guard.py`
  - `python3 -m pytest tests/test_graphify_vault_loop.py -q`
  - `python3 scripts/quality/metric_snapshot.py`

## Deliverable
- commit(s): pending
- metric delta: broad exceptions 30 -> 8; print calls 168 -> 50; long functions 34 -> 15 after explicit JSON/OSError/YAML catches plus helper extraction across lockfile, scan_code, graphify loop, dashboard/cost/scoring, migration worker, asset registry, MCP audit status, selftest, and restructure paths
- residual risk: 8 broad catches remain, led by core atomic-write/dogfood/eval boundary/fail-open paths where broad catch is still intentional or requires deeper behavioral review.
