You are an independent adversarial quality evaluator for auto-pilot v0.8.7 iteration 8 / wave 7.

Repo: /Users/lyan/.config/superpowers/worktrees/auto-pilot/v087-quality-90
Current HEAD: evaluate the live checkout with `git rev-parse HEAD` (this prompt file may be committed later; do not reject solely for prompt SHA mismatch).
Baseline: v0.8.6 shipped score was 84.40/100 after local gates + hosted CI green.
Rubric SoT: skills/quality-eval/SKILL.md and skills/quality-eval/references/rubric-dims.md.

Task: rescore conservatively after commits 73127ae..HEAD plus the current Wave 7 working tree if this prompt is evaluated before commit. Do not claim release completion. Penalize inflation. Any +5 or larger dimension lift needs concrete evidence from files/metrics/commits below.

Evidence from v0.8.7 branch:
- Commits through HEAD before this prompt update:
a8f49c3 test(quality): add debt metric snapshot
b26b475 docs(quality): add v0.8.7 worker contracts
5fc92a6 refactor(vault): expand strict mypy pilot scope
5212f24 fix(vault): narrow quality-loop error handling
2c5e88e refactor(vault): standardize script output helpers
fbe8d30 refactor: split quality-loop long functions
9299e7c fix(vault): narrow wave one error handlers
bbce793 test(graphify): cover query artifact exports
24d4513 refactor: complete wave two quality cleanup
0a3d3e9 chore(quality): record final v087 metrics
209a7c6 docs(quality): add v087 rescore prompt
cb1f5bb refactor: address codex v087 quality rejection
680852a docs(quality): refresh v087 final rescore prompt
403283e refactor: lift v087 quality after adversarial rescore
ff8b23d chore(quality): record v087 rescore block
9c074b4 docs(quality): note ci coverage floor lift
985cc6e refactor: add wave five quality evidence gates
dd2e41b refactor: eliminate wave six quality debt metrics
- Wave 6 evidence:
  - long_functions_gt40=0 and broad_exceptions=0 after core helper extraction in dispatch, worktree, reviewer wrapper, source adapter bootstrap, doc citation loop, snapshot verification, selftest, and narrowed exception tuples in _contract, _dogfood_gate, eval runner, export, MCP server, and restructure loop.
  - Graphify query suite updated and rerun 27/27; WorktreeManager -> .apply_to_main() path limitation became a passing path test.
- Wave 7 evidence:
  - production raw print_calls=0 after converting remaining CLI/report outputs to sys.stdout/sys.stderr stream writes while preserving stdout/stderr contracts.
  - pytest parametrize markers increased 9 -> 12 via metric snapshot scope/subprocess/shell parametrization tests.
- Metrics from scripts/quality/metric_snapshot.py (production scope: excludes tests/, __pycache__, and test_*.py hook selftests):
  - baseline v0.8.6 detailed metric: long_functions_gt40=34, broad_exceptions=30, print_calls=168, scripts coverage 80.06%, root pytest 595 passed, vault pytest 91 passed, strict vault mypy pilots=2, event() calls=37, pytest parametrize markers=6.
  - wave5: long_functions_gt40=11, broad_exceptions=8, print_calls=37, subprocess_without_timeout=0, shell_true_calls=0, event_calls=55, scripts coverage 87.58%, root pytest 613 passed, vault pytest 106 passed, strict mypy source files=51, strict vault mypy pilots=16.
  - wave6: long_functions_gt40=0, broad_exceptions=0, print_calls=37, subprocess_without_timeout=0, shell_true_calls=0, event_calls=55, scripts coverage 87.75%, root pytest 613 passed, vault pytest 106 passed, strict mypy source files=51, strict vault mypy pilots=16, Graphify query_passed=27/query_total=27.
  - final wave7: long_functions_gt40=0, broad_exceptions=0, print_calls=0, subprocess_without_timeout=0, shell_true_calls=0, event_calls=55, scripts coverage 87.80%, root pytest 622 passed, vault pytest 106 passed, strict mypy source files=51, strict vault mypy pilots=16, pytest parametrize markers=12, Graphify query_passed=27/query_total=27.
- Local verification at Wave 7:
  - python3 -m pytest tests/ -q => 622 passed.
  - (cd vault && python3 -m pytest tests/ -q) => 106 passed.
  - python3 -m pytest tests/ -q --cov=scripts --cov-fail-under=80 => 622 passed, scripts coverage 87.80%.
  - python3 -m mypy => Success: no issues found in 51 source files.
  - python3 -m ruff check scripts/ tests/ hooks/ vault/ => All checks passed.
  - python3 hooks/test_guard_destructive.py && python3 hooks/test_codex_conductor_guard.py && python3 hooks/test_notebooklm_delete_gate.py => 13/13, 9/9, 9/9 passed.
  - bats skills/adversarial-review-loop/tests => 40 passed; bats skills/setup-harness/tests => 47 passed.
  - bash scripts/quality/check-module-size.sh => OK.
  - python3 scripts/docs/check_doc_reference_integrity.py => OK.
  - python3 skills/doc-management/scripts/check_design_doc_freshness.py => 0 STALE, WARN-only doc root missing .claude/design.
  - graphify update . --force then python3 scripts/graphify_vault_loop.py --vault /Users/lyan/Documents/Knowledge/wiki/projects/auto-pilot --compact --max-iterations 2 => ok true, query_passed=27/query_total=27.
- Earlier v0.8.7 changes still in scope:
  - scripts/quality/metric_snapshot.py added and extended with subprocess_without_timeout, shell_true_calls, event_calls; tests cover these metrics.
  - mypy.ini strict scope expanded from 2 vault pilots to 16 vault files, including source adapter protocol and drift detector; tests/test_mypy_scope.py guards scope.
  - scripts/graphify_vault_loop.py default_runner has a 120s subprocess timeout with tests.
  - scripts/evals/oracle_api.py no longer uses shell=True; tests assert argv form and timeout.
  - CI coverage floor raised 75 -> 80 and guarded by tests/test_ci_workflow_vault_gates.py.
  - tests/test_asset_registry_check.py and parametrized NotebookLM classifier tests added.

Scoring dimensions and weights: type_safety .09, test_quality .13, error_handling .10, code_structure .09, configuration .07, logging .09, async_correctness .10, documentation .07, security .07, architecture .05, performance_budget .06, llm_prompt_quality .05, ci_cd_quality .03.

Output concise markdown with a JSON score block and adversarial notes. Score must be evidence-backed and conservative. If below 90, say so plainly.
