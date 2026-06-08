You are an independent adversarial quality evaluator for auto-pilot v0.8.7 iteration 8 / wave 10.

Repo: /Users/lyan/.config/superpowers/worktrees/auto-pilot/v087-quality-90
Current checkout: committed or live Wave 10 working tree; run `git rev-parse HEAD` and inspect `git diff` if needed.
Baseline: v0.8.6 shipped weighted score was 84.40/100 after local gates + hosted CI green.
Rubric SoT: skills/quality-eval/SKILL.md and skills/quality-eval/references/rubric-dims.md.

Task: rescore conservatively after Wave 10 changes. Do not claim release completion. Penalize inflation. Any +5 or larger dimension lift needs concrete evidence from files/metrics/commits below.

Prior adversarial scores:
- Codex r1: .planning/quality/eval-codex-8.json => 87.33, REJECT_FOR_90_TARGET.
- Claude wave8: .planning/quality/claude-8-wave8/raw.md => 88.57, BELOW_90.
- Claude wave9: .planning/quality/claude-8-wave9/raw.md => JSON weighted_total=90.17, conservative recalculation=90.03, MEETS_90_TARGET.
- Codex wave9 r2: .planning/quality/codex-8-wave9-r2/last-message.md => 89.93, BELOW_90. Main blockers: prompt-output sanitizer/budget cap missing, perf cold-start/p99/throughput absent, architecture remains 84.

Wave 10 evidence directly addressing Codex wave9 r2 blockers:
- LLM prompt quality: scripts/_prompts.py adds `sanitize_for_llm()` and `render_for_llm()` for the LLM-call boundary while preserving raw `render()` template semantics. The safe boundary redacts secret-like assignments, bearer/OpenAI-style keys, strips ANSI escapes and non-printing control chars, and enforces `MAX_LLM_PROMPT_CHARS`.
- Prompt output path: scripts/headless-loop.py now applies `_prompts.sanitize_for_llm()` before spawning Claude and uses `_prompts.render_for_llm()` for iteration prompts.
- Prompt tests: tests/test_prompt_regression.py verifies secret-like prompt-output redaction, ANSI/control scrub, and prompt budget enforcement. tests/test_headless_loop_cli.py verifies the final subprocess prompt is sanitized before spawn.
- Prompt docs: docs/prompt-quality.md documents template-layer vs LLM-call-boundary contracts and lists regression evidence. docs/README.md links it.
- Performance budget: tests/test_perf.py adds `test_cli_import_cold_start_under_budget` (<2s fresh Python import of CLI hot modules). .github/workflows/ci.yml runs it as explicit `perf cold-start ceiling`; tests/test_ci_workflow_vault_gates.py guards the CI step. docs/perf-budget.md documents the cold-start gate.

Wave 10 metric snapshot from .planning/quality/v087-wave10-final-metrics.json:
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

Wave 10 local verification:
- python3 -m pytest tests/ -q => 699 passed.
- (cd vault && python3 -m pytest tests/ -q) => 106 passed.
- python3 -m pytest tests/ -q --cov=scripts --cov-fail-under=80 => 699 passed, scripts coverage 91.54%.
- python3 -m mypy => Success: no issues found in 51 source files.
- python3 -m ruff check scripts/ tests/ hooks/ vault/ => All checks passed.
- bash scripts/quality/check-module-size.sh => OK.
- python3 scripts/docs/check_doc_reference_integrity.py => OK.
- hook selftests: 13/13, 9/9, 9/9 passed.
- bats: adversarial-review-loop 40/40, setup-harness 47/47 passed.
- python3 -m pytest tests/test_perf.py --benchmark-only -v => 4 passed, 2 skipped non-benchmark tests.
- python3 -m pytest tests/test_perf.py::test_rss_under_ceiling tests/test_perf.py::test_cli_import_cold_start_under_budget -q => 2 passed.
- graphify update . --force succeeded; python3 scripts/graphify_vault_loop.py --vault /Users/lyan/Documents/Knowledge/wiki/projects/auto-pilot --compact --max-iterations 2 => 27/27 query suite passed.

Carried-forward Wave 9 evidence still valid:
- `_contract.py` and `_dispatch.py` no longer use `typing.Any` or `dict[str, Any]` for core contract/ticket/review domain payloads; they use JsonObject/narrowers.
- duration_ms event fields exist around external git subprocesses in risk_assess and _dispatch.
- tests/test_perf.py enforces mean <50ms, p95 <50ms when sample data exists, and committed baseline mean for all 4 benchmarks.
- schemas/prompt-fixture.schema.json validates all prompt fixtures; 20 fixtures, 5 adversarial.
- tests/test_dispatch.py validates structured reviewer LLM output schema accepts valid output and rejects unstructured extra fields.
- CI has pip-audit, gitleaks, coverage >=80, vault pytest, benchmark, RSS, cold-start, shellcheck, hooks, bats, manifest and prompt fixture JSON checks.

Scoring dimensions and weights: type_safety .09, test_quality .13, error_handling .10, code_structure .09, configuration .07, logging .09, async_correctness .10, documentation .07, security .07, architecture .05, performance_budget .06, llm_prompt_quality .05, ci_cd_quality .03.

Output concise markdown with a JSON score block and adversarial notes. Score must be evidence-backed and conservative. If below 90, say so plainly.
