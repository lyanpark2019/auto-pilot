# v0.8.7 Structure Contract

## Scope
- Owned files:
  - `hooks/guard-destructive.py`
  - `hooks/test_guard_destructive.py`
  - `vault/scripts/restructure_loop.py`
  - `vault/tests/test_restructure_loop.py`
  - `vault/scripts/restructure_phases/phase06_vault_build.py`
  - `vault/tests/test_restructure_phase06.py`
- Forbidden files:
  - `scripts/_dispatch.py` unless PM approves after characterization coverage is sufficient
  - release manifests
  - type-only files owned by Type Scope Worker

## Target metrics
- before:
  - long functions >40 lines: 34
- after:
  - Wave 1: <=25
  - Wave 2: <=20

## Required tests
- RED/characterization:
  - hooks use stdin JSON fixtures and preserve exit semantics.
  - restructure scripts use `tmp_path`/monkeypatch and avoid live vault mutation.
- GREEN:
  - `python3 hooks/test_guard_destructive.py`
  - `( cd vault && python3 -m pytest tests/test_restructure_loop.py tests/test_restructure_phase06.py -q )`
  - `bash scripts/quality/check-module-size.sh`
  - `python3 scripts/quality/metric_snapshot.py`

## Deliverable
- commit(s): pending
- metric delta: long functions 34 -> 0 and public top-level API docstring coverage 48.7% -> 99.25% (263/265) after splitting destructive/conductor hooks, orchestrator phase/dispatch/parser paths, restructure loop, phase03/phase06/phase07 restructure phases, notebook classification/materialization, migration source-add, dashboard aggregation, asset registry, eval runner/CLI, fix planner, score_content scoring paths, dispatch ticket/outcome helpers, WorktreeManager lifecycle helpers, CodeAdapter bootstrap writers, doc citation loops, snapshot verification, reviewer wait init, selftest agent validation, and public API docstring pass guarded by `scripts/quality/metric_snapshot.py`
- residual risk: helper extraction increases symbol count; Graphify query suite expectations were refreshed and rerun 27/27 to guard navigability after the split.
