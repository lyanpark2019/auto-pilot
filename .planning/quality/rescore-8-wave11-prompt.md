You are an independent adversarial quality evaluator for auto-pilot v0.8.7 iteration 8 / wave 11.

Repo: /Users/lyan/.config/superpowers/worktrees/auto-pilot/v087-quality-90
Current checkout: committed or live Wave 11 working tree; run `git rev-parse HEAD` and inspect `git diff` if needed.
Baseline: v0.8.6 shipped weighted score was 84.40/100 after local gates + hosted CI green.
Rubric SoT: skills/quality-eval/SKILL.md and skills/quality-eval/references/rubric-dims.md.

Task: rescore conservatively after Wave 11 changes. Do not claim release completion. Penalize inflation.

Prior adversarial scores:
- Claude wave9: .planning/quality/claude-8-wave9/raw.md => conservative recalculation=90.03, MEETS_90_TARGET.
- Codex wave9 r2: .planning/quality/codex-8-wave9-r2/last-message.md => 89.93, BELOW_90.
- Codex wave10: .planning/quality/codex-8-wave10/last-message.md => 89.99, BELOW_90. It raised performance_budget 89->90 but held llm_prompt_quality at 89 because sanitizer leaked `token="..."`, `"api_key": "..."`, and `Authorization: Bearer ...` forms.

Wave 11 evidence directly addressing the Codex wave10 blocker:
- scripts/_prompts.py now redacts bare, quoted, JSON-shaped, Authorization Bearer, and raw `sk-*` secret-like forms at the LLM-call boundary.
- tests/test_prompt_regression.py adds a parametrized regression for Codex's three exact leak examples: `token="secret-value-123456"`, `{"api_key": "secret-value-123456"}`, and `Authorization: Bearer abcdefgh123456`.
- docs/prompt-quality.md documents quoted/JSON-shaped secret field redaction and Authorization Bearer redaction.
- scripts/headless-loop.py still applies `_prompts.sanitize_for_llm()` before spawning Claude and `_prompts.render_for_llm()` for iteration prompts.

Wave 11 metric snapshot from .planning/quality/v087-wave11-final-metrics.json:
- long_functions_gt40=0
- broad_exceptions=0
- print_calls=0
- subprocess_without_timeout=0
- shell_true_calls=0
- event_calls=59
- public_api_total=268
- public_api_with_docstring=266
- public_api_docstring_coverage_pct=99.25
- prompt_fixtures=20
- adversarial_prompt_fixtures=5
- core_any_hits in `_contract.py`/`_dispatch.py`=0
- prompt_module_any_hits in `_prompts.py`=0

Wave 11 local verification:
- python3 -m pytest tests/ -q => 702 passed.
- (cd vault && python3 -m pytest tests/ -q) => 106 passed.
- python3 -m pytest tests/ -q --cov=scripts --cov-fail-under=80 => 702 passed, scripts coverage 91.56%.
- python3 -m mypy => Success: no issues found in 51 source files.
- python3 -m ruff check scripts/ tests/ hooks/ vault/ => All checks passed.
- bash scripts/quality/check-module-size.sh => OK.
- python3 scripts/docs/check_doc_reference_integrity.py => OK.
- hook selftests: 13/13, 9/9, 9/9 passed.
- bats: adversarial-review-loop 40/40, setup-harness 47/47 passed.
- python3 -m pytest tests/test_perf.py --benchmark-only -v => 4 passed, 2 skipped non-benchmark tests.
- python3 -m pytest tests/test_perf.py::test_rss_under_ceiling tests/test_perf.py::test_cli_import_cold_start_under_budget -q => 2 passed.
- graphify update . --force succeeded; graphify query suite via scripts/graphify_vault_loop.py => 27/27 passed.

Carried-forward Wave 10 evidence still valid:
- Performance budget now has mean, p95, committed baseline, RSS ceiling, and cold-start ceiling, with explicit CI steps for benchmark, memory, and cold-start.
- LLM prompt boundary has safe render/sanitize functions, prompt-output path in headless-loop, schema-backed fixture suite, 20 fixtures, 5 adversarial fixtures, and structured reviewer output schema tests.
- CI has pip-audit, gitleaks, coverage >=80, vault pytest, benchmark, RSS, cold-start, shellcheck, hooks, bats, manifest, and prompt fixture JSON checks.

Scoring dimensions and weights: type_safety .09, test_quality .13, error_handling .10, code_structure .09, configuration .07, logging .09, async_correctness .10, documentation .07, security .07, architecture .05, performance_budget .06, llm_prompt_quality .05, ci_cd_quality .03.

Output concise markdown with a JSON score block and adversarial notes. Score must be evidence-backed and conservative. If below 90, say so plainly.
