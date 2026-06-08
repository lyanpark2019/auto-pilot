# v0.8.7 Test CI Score Contract

## Scope
- Owned files:
  - `tests/test_headless_loop.py`
  - `tests/test_headless_loop_cli.py`
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
- metric delta: root scripts coverage 80.06% -> 91.63%; CI coverage floor 75 -> 80; root suite 595 -> 665 passed and vault suite 91 -> 106 passed; pytest parametrize markers 6 -> 18; prompt regression fixtures guarded at 20; headless-loop.py coverage 54% -> 97% and risk_assess.py 75% -> 97% after graphify artifact/manifest characterization tests, asset registry scanner coverage, Graphify timeout regression tests, subprocess-timeout metric tests, metric scope/timeout/shell/docstring parametrization, eval oracle no-shell regression, headless subprocess/CLI coverage, direct risk-assessment branch coverage, refreshed Graphify helper expectations, and parametrized NotebookLM classifier cases
- residual risk: if final score remains below 90, stop before release and ask whether to ship a sub-90 release.
