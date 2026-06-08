You are an independent adversarial quality evaluator for auto-pilot v0.8.7 iteration 8.

Repo: /Users/lyan/.config/superpowers/worktrees/auto-pilot/v087-quality-90
Current HEAD: evaluate the live checkout with `git rev-parse HEAD` (this prompt file is committed on the same branch, so do not reject solely for a self-referential prompt SHA mismatch).
Baseline: v0.8.6 shipped score was 84.40/100 after local gates + hosted CI green.
Rubric SoT: skills/quality-eval/SKILL.md and skills/quality-eval/references/rubric-dims.md.

Task: rescore conservatively after commits 73127ae..HEAD. Do not claim release completion. Penalize inflation. Any +5 or larger dimension lift needs concrete evidence from files/metrics/commits below.

Evidence from v0.8.7 branch:
- Commits:
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
- Metrics from scripts/quality/metric_snapshot.py:
  - baseline v0.8.6 detailed metric: long_functions_gt40=34, broad_exceptions=30, print_calls=168, scripts coverage 80.06%, root pytest 595 passed, vault pytest 91 passed, strict vault mypy pilots=2, event() calls=37, pytest parametrize markers=6.
  - final v0.8.7: long_functions_gt40=11, broad_exceptions=8, print_calls=50, scripts coverage 87.50%, root pytest 611 passed, vault pytest 106 passed, strict mypy source files=49, strict vault mypy pilots=14, event() calls=56, pytest parametrize markers=9.
- Local verification at HEAD:
  - python3 -m pytest tests/ -q => 611 passed.
  - (cd vault && python3 -m pytest tests/ -q) => 106 passed.
  - python3 -m pytest tests/ -q --cov=scripts --cov-fail-under=80 => 611 passed, scripts coverage 87.50%.
  - python3 -m mypy => Success: no issues found in 49 source files.
  - python3 -m ruff check scripts/ tests/ hooks/ vault/ => All checks passed.
  - python3 hooks/test_guard_destructive.py && python3 hooks/test_codex_conductor_guard.py && python3 hooks/test_notebooklm_delete_gate.py => 13/13, 9/9, 9/9 passed.
  - bats skills/adversarial-review-loop/tests => 40 passed; bats skills/setup-harness/tests => 47 passed.
  - bash scripts/quality/check-module-size.sh => OK.
  - python3 scripts/docs/check_doc_reference_integrity.py => OK.
  - python3 skills/doc-management/scripts/check_design_doc_freshness.py => 0 STALE, WARN-only doc root missing .claude/design.
  - graphify update . --force then python3 scripts/graphify_vault_loop.py --vault /Users/lyan/Documents/Knowledge/wiki/projects/auto-pilot --compact --max-iterations 2 => ok true, query_passed=27/query_total=27.
- Major changes:
  - scripts/quality/metric_snapshot.py added with tests/test_quality_metric_snapshot.py.
  - mypy.ini strict scope expanded from 2 vault pilots to 14 vault files; tests/test_mypy_scope.py guards scope.
  - Broad exception cleanup lowered broad handlers 30 -> 8.
  - Raw print cleanup lowered print calls 168 -> 50; event() calls increased 37 -> 56 via structured logs in asset registry, eval runner/CLI, and graphify query loop.
  - Long function cleanup lowered >40-line functions 34 -> 11.
  - scripts/graphify_vault_loop.py default_runner now has a 120s subprocess timeout with tests.
  - tests/test_asset_registry_check.py and parametrized NotebookLM classifier tests added; scripts coverage moved 80.06% -> 87.50%.
  - Orchestrator phase/dispatch/parser functions split while preserving tests and perf benchmarks.

Scoring dimensions and weights: type_safety .09, test_quality .13, error_handling .10, code_structure .09, configuration .07, logging .09, async_correctness .10, documentation .07, security .07, architecture .05, performance_budget .06, llm_prompt_quality .05, ci_cd_quality .03.

Output requirements:
- Output concise markdown with a JSON score block and adversarial notes.
- Score must be evidence-backed and conservative. If below 90, say so plainly.
