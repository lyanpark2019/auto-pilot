You are an independent adversarial quality evaluator for auto-pilot v0.8.7 iteration 8.

Repo: /Users/lyan/.config/superpowers/worktrees/auto-pilot/v087-quality-90
Current HEAD: 29f9fa0a48ad8cb3e648b4a41e8e733d0b09cb67 (29f9fa0)
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
29f9fa0 docs(quality): add v087 rescore prompt
- Metrics from scripts/quality/metric_snapshot.py:
  - baseline v0.8.6 detailed metric: long_functions_gt40=34, broad_exceptions=30, print_calls=168, scripts coverage 80.06%, root pytest 595 passed, vault pytest 91 passed, strict vault mypy pilots=2.
  - final v0.8.7: long_functions_gt40=20, broad_exceptions=14, print_calls=77, scripts coverage 81.33%, root pytest 600 passed, vault pytest 97 passed, strict mypy source files=43, strict vault mypy pilots=8.
- Local verification at HEAD:
  - python3 -m pytest tests/ -q => 600 passed.
  - (cd vault && python3 -m pytest tests/ -q) => 97 passed.
  - python3 -m mypy => Success: no issues found in 43 source files.
  - python3 -m ruff check scripts/ tests/ hooks/ vault/ => All checks passed.
  - python3 hooks/test_guard_destructive.py && python3 hooks/test_codex_conductor_guard.py && python3 hooks/test_notebooklm_delete_gate.py => 13/13, 9/9, 9/9 passed.
  - bats skills/adversarial-review-loop/tests => 40 passed; bats skills/setup-harness/tests => 47 passed.
  - bash scripts/quality/check-module-size.sh => OK.
  - python3 scripts/docs/check_doc_reference_integrity.py => OK.
  - python3 skills/doc-management/scripts/check_design_doc_freshness.py => 0 STALE, WARN-only doc root missing .claude/design.
  - graphify update . --force then python3 scripts/graphify_vault_loop.py --vault /Users/lyan/Documents/Knowledge/wiki/projects/auto-pilot --compact --max-iterations 2 => ok true, query_passed=27/query_total=27.
- Major changes:
  - scripts/quality/metric_snapshot.py added with tests/test_quality_metric_snapshot.py.
  - mypy.ini strict scope expanded to vault/pipeline/{bases,dispatch,loop,scan_docs,self_improve,state}.py plus prior vault/pipeline/canvas.py and vault/sources/code.py; tests/test_mypy_scope.py guards scope.
  - Broad exception cleanup in vault/scripts/lockfile.py, vault/pipeline/scan_code.py, hooks/codex-conductor-guard.py, scripts/graphify_vault_loop.py, vault/scripts/{cost_tracker,dashboard_data,score_content,score_structural}.py, vault/scripts/migrate/pm.py, vault/scripts/migrate/worker.py, vault/scripts/restructure_phases/phase07_notebooklm_create.py.
  - Raw print cleanup in vault pipeline/scripts plus scripts/orchestrator.py; CLI stdout/stderr behavior preserved with stream helpers.
  - Long function splits in hooks/guard-destructive.py, hooks/codex-conductor-guard.py, vault/scripts/restructure_loop.py, vault/scripts/restructure_phases/phase03_sportic365_merge.py, phase06_vault_build.py, phase07_notebooklm_create.py, vault/sources/notebooklm.py, vault/scripts/dashboard_data.py, vault/scripts/migrate/worker.py, vault/scripts/score_content.py.
  - Graphify query artifact tests added; scripts coverage moved 80.06% -> 81.33%.

Scoring dimensions and weights: type_safety .09, test_quality .13, error_handling .10, code_structure .09, configuration .07, logging .09, async_correctness .10, documentation .07, security .07, architecture .05, performance_budget .06, llm_prompt_quality .05, ci_cd_quality .03.

Output requirements:
- Codex track: output ONLY valid JSON with keys: head_sha, weighted_score, scores, weighted_score_computation, residual_risks, verdict.
- Claude track: if you are Claude, output concise markdown with a JSON score block and adversarial notes.
- Score must be evidence-backed and conservative. If below 90, say so plainly.
