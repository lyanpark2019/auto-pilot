# v0.8.7 Test CI Score Contract

## Scope
- Owned files:
  - `tests/test_headless_loop.py`
  - `tests/test_graphify_vault_loop.py`
  - `.github/workflows/ci.yml` only if parity drifts
  - `.planning/quality/v087-*.json`
  - `.planning/quality/eval-codex-8.json`
  - `.planning/quality/eval-claude-8.md`
  - `.planning/quality/score-state.json` during final rescore only
- Forbidden files:
  - release manifests until final release task
  - worker-owned implementation files unless fixing test integration

## Target metrics
- before:
  - root tests: 595 passed
  - vault tests: 91 passed
  - scripts coverage: 80.06%
  - hosted CI: green on v0.8.6
- after:
  - root/vault suites green
  - scripts coverage stays >=80%, preferably >=81%
  - hosted CI green on release SHA
  - final weighted score >=90 after dual rescore

## Required tests
- RED/characterization:
  - add weak-branch coverage without spawning real Claude or Graphify.
- GREEN:
  - `python3 -m pytest tests/test_headless_loop.py tests/test_graphify_vault_loop.py -q`
  - `python3 -m pytest tests/ -q --cov=scripts --cov-fail-under=80`
  - full local gates before release

## Deliverable
- commit(s): pending
- metric delta: root scripts coverage 80.06% -> 81.28%; root suite 595 -> 600 passed after graphify artifact/manifest characterization tests
- residual risk: if final score remains below 90, stop before release and ask whether to ship an 87-89 release.
