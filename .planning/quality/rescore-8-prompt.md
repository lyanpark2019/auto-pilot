You are an independent adversarial quality evaluator for auto-pilot v0.8.7 iteration 8 / wave 8.

Repo: /Users/lyan/.config/superpowers/worktrees/auto-pilot/v087-quality-90
Current checkout: committed Wave 8 HEAD; run `git rev-parse HEAD` for the exact SHA.
Baseline: v0.8.6 shipped weighted score was 84.40/100 after local gates + hosted CI green.
Rubric SoT: skills/quality-eval/SKILL.md and skills/quality-eval/references/rubric-dims.md.

Task: rescore conservatively after commits 73127ae..HEAD plus Wave 8 changes in this working tree. Do not claim release completion. Penalize inflation. Any +5 or larger dimension lift needs concrete evidence from files/metrics/commits below.

Commit history: run `git log --oneline --reverse 73127ae..HEAD`; the latest commit is the Wave 8 quality-evidence commit (`refactor: strengthen wave eight quality evidence`).

Prior adversarial scores:
- Codex r1: .planning/quality/eval-codex-8.json => 87.33, REJECT_FOR_90_TARGET.
- Claude wave4: .planning/quality/eval-claude-8.md => 82.78, BELOW_90.
- Claude wave5: 83.42, BELOW_90.
- Claude wave6: 85.57, BELOW_90.
- Claude wave7: .planning/quality/claude-8-wave7/raw.md => 84.45, BELOW_90. Its stated blockers were documentation 76, test_quality 83, configuration 82, logging 84, performance_budget 81, type_safety 85, llm_prompt_quality 82.

Wave 8 evidence directly addressing those blockers:
- Documentation: scripts/quality/metric_snapshot.py now reports public API docstring metrics. Current production top-level public API docstring coverage is 263/265 = 99.25% (previous top-level local count before the pass was 129/265 = 48.7%; Claude wave7 cited 106/156 = 67.9%). Missing hits are only scripts/docs/check_doc_reference_integrity.py Violation/main, intentionally skipped to avoid module-size growth in an already 499-line guard file.
- Test quality: root tests increased 622 -> 665 passed; scripts coverage increased 87.80% -> 91.63%; headless-loop.py coverage increased 54% -> 97%; risk_assess.py coverage increased 75% -> 97%; pytest parametrize markers increased 12 -> 18. Added tests/test_headless_loop_cli.py for subprocess streaming/timeouts, run_claude_session, CLI terminal exit paths, and stash timeout/failure paths. Added direct risk_assess branch tests for extension edges, Assessment.to_json, changed_files_from_git success/failure, main stdin, and diff timeout handling.
- Configuration: added docs/configuration.md with env var/default/bounds/consumer matrix and profile note. tests/test_config.py guards CLAUDE_BIN, AUTO_PILOT_PREFLIGHT_TTL_SEC, and all AutoPilotConfig public default fields in docs. Existing config tests still cover every numeric lower/upper bound and env override.
- Logging/security: scripts/_log.py now redacts secret-like keys (api_key/token/password/secret/credential/authorization/auth) and secret-like values (Bearer, sk-*, gh*_*) before writing event records. tests/test_log.py proves raw secret values do not appear in stderr. print_calls remain 0; event() calls remain 55.
- Performance budget: tests/test_perf.py now applies the committed baseline regression assertion to all 4 benchmarks including pivot_check/risk_assess. tests/perf_baseline.json already has all 4 baseline entries. docs/perf-budget.md documents absolute + baseline gates and refresh procedure.
- LLM prompt quality: prompts/fixtures has 20 JSON regression fixtures; tests/test_prompt_regression.py enforces >=20 and fixture rendering. This corrects the old wave7 prompt/eval note that counted 10 fixtures.
- Security/CI correction: .github/workflows/ci.yml already has separate pip-audit and gitleaks jobs; tests/test_ci_workflow_vault_gates.py now explicitly guards both plus the perf benchmark gate. Do not penalize as absent unless your live file inspection proves otherwise.

Wave 8 metric snapshot from .planning/quality/v087-wave8-final-metrics.json:
- long_functions_gt40=0
- broad_exceptions=0
- print_calls=0
- subprocess_without_timeout=0
- shell_true_calls=0
- event_calls=55
- public_api_total=265
- public_api_with_docstring=263
- public_api_docstring_coverage_pct=99.25
- prompt_fixtures=20
- pytest parametrize markers=18

Wave 8 local verification:
- python3 -m pytest tests/ -q => 665 passed.
- (cd vault && python3 -m pytest tests/ -q) => 106 passed.
- python3 -m pytest tests/ -q --cov=scripts --cov-fail-under=80 => 665 passed, scripts coverage 91.63%.
- python3 -m mypy => Success: no issues found in 51 source files.
- python3 -m ruff check scripts/ tests/ hooks/ vault/ => All checks passed.
- bash scripts/quality/check-module-size.sh => OK.
- python3 scripts/docs/check_doc_reference_integrity.py => OK.
- hook selftests => 13/13, 9/9, 9/9 passed.
- bats skills/adversarial-review-loop/tests => 40 passed; bats skills/setup-harness/tests => 47 passed.
- python3 skills/doc-management/scripts/check_design_doc_freshness.py => 0 STALE, WARN-only .claude/design missing.
- graphify update . --force then python3 scripts/graphify_vault_loop.py --vault /Users/lyan/Documents/Knowledge/wiki/projects/auto-pilot --compact --max-iterations 2 => ok true, query_passed=27/query_total=27.

Carried-forward Wave 7/Wave 6 evidence still valid:
- production raw print_calls=0 after stream-write conversion while preserving CLI stdout/stderr contracts.
- long_functions_gt40=0 and broad_exceptions=0 after helper extraction and exception narrowing.
- subprocess_without_timeout=0 and shell_true_calls=0.
- strict mypy source files=51; strict vault mypy pilots=16.
- CI coverage floor raised 75 -> 80.
- Graphify query suite passed 27/27 after Wave 8 graphify update.

Scoring dimensions and weights: type_safety .09, test_quality .13, error_handling .10, code_structure .09, configuration .07, logging .09, async_correctness .10, documentation .07, security .07, architecture .05, performance_budget .06, llm_prompt_quality .05, ci_cd_quality .03.

Output concise markdown with a JSON score block and adversarial notes. Score must be evidence-backed and conservative. If below 90, say so plainly.
