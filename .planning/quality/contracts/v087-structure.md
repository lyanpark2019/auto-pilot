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
- metric delta: long functions 34 -> 15 after splitting destructive/conductor hooks, restructure loop, phase03/phase06/phase07 restructure phases, notebook classification/materialization, migration source-add, dashboard aggregation, asset registry, eval runner/CLI, fix planner, and score_content scoring paths
- residual risk: 15 long functions remain, led by core scripts `_dispatch.py`, `orchestrator.py`, `_worktree.py`, `_reviewer_wrapper.py`, and doc citation integrity; defer deeper core orchestration refactors until stronger characterization coverage exists.
