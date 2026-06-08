You are an independent adversarial quality evaluator for auto-pilot v0.8.7 iteration 8 / wave 9.

Repo: /Users/lyan/.config/superpowers/worktrees/auto-pilot/v087-quality-90
Current checkout: committed or live Wave 9 working tree; run `git rev-parse HEAD` and inspect `git diff` if needed.
Baseline: v0.8.6 shipped weighted score was 84.40/100 after local gates + hosted CI green.
Rubric SoT: skills/quality-eval/SKILL.md and skills/quality-eval/references/rubric-dims.md.

Task: rescore conservatively after Wave 9 changes. Do not claim release completion. Penalize inflation. Any +5 or larger dimension lift needs concrete evidence from files/metrics/commits below.

Prior adversarial scores:
- Codex r1: .planning/quality/eval-codex-8.json => 87.33, REJECT_FOR_90_TARGET.
- Claude wave4: .planning/quality/eval-claude-8.md => 82.78, BELOW_90.
- Claude wave7: .planning/quality/claude-8-wave7/raw.md => 84.45, BELOW_90.
- Claude wave8: .planning/quality/claude-8-wave8/raw.md => 88.57, BELOW_90. Remaining blockers: core Any density, no latency logs, no p95/memory perf CI visibility, prompt structured/adversarial schema evidence, pydantic preference, docstring depth, architecture coupling.

Wave 9 evidence directly addressing the blockers:
- Type safety: `_contract.py` and `_dispatch.py` no longer use `typing.Any` or `dict[str, Any]` for contract/ticket/review domain payloads. They now use `JsonObject = dict[str, object]` plus `_as_str`, `_as_int`, `_as_object`, `_optional_str`, and `_as_str_list` narrowers. `rg 'dict\[str, Any\]|from typing import Any' scripts/_contract.py scripts/_dispatch.py` returns 0 hits. `python3 -m mypy` still passes over 51 source files.
- Logging: `scripts/_log.py` redacts secret-like keys/values; Wave 9 adds `duration_ms` event fields around external git subprocesses in `risk_assess.changed_files_from_git`, `_dispatch._check_preflight_head_sha`, `_dispatch.freeze_diff_for_review`, and `_dispatch.assert_reviewer_was_scoped`. event() call count increased 55 -> 59; print_calls remain 0.
- Performance budget: `tests/test_perf.py` now enforces mean <50ms, p95 <50ms when pytest-benchmark sample data is available, and committed baseline mean for all 4 benchmarks. CI now has explicit `perf memory ceiling` step for `tests/test_perf.py::test_rss_under_ceiling`; docs/perf-budget.md documents mean/p95/baseline/RSS gates.
- LLM prompt quality / structured output: added `schemas/prompt-fixture.schema.json`; every `prompts/fixtures/*.json` is schema-validated in tests. `prompts/fixtures` has 20 fixtures, 5 marked adversarial (`prompt-injection`, `unicode-confusables`, `control-chars-ansi`, `markdown-breaking`, `json-in-var`). `tests/test_dispatch.py` now explicitly validates the structured reviewer LLM output schema (`schemas/review.schema.json`) accepts valid output and rejects extra unstructured fields.
- CI/security visibility: `.github/workflows/ci.yml` already has pip-audit and gitleaks jobs; tests guard those plus the perf benchmark and memory gates.
- Configuration: docs/configuration.md documents env vars/defaults/bounds/consumers and explicitly explains the stdlib-only choice instead of runtime pydantic dependency; tests guard doc drift and every bound. Do not require adding pydantic if you accept the repo constraint that helper modules are stdlib-only at plugin runtime.

Wave 9 metric snapshot from .planning/quality/v087-wave9-final-metrics.json:
- long_functions_gt40=0
- broad_exceptions=0
- print_calls=0
- subprocess_without_timeout=0
- shell_true_calls=0
- event_calls=59
- public_api_total=265
- public_api_with_docstring=263
- public_api_docstring_coverage_pct=99.25
- pytest parametrize markers=20
- prompt_fixtures=20
- adversarial_prompt_fixtures=5
- core Any hits in `_contract.py`/`_dispatch.py`=0

Wave 9 local verification:
- python3 -m pytest tests/ -q => 694 passed.
- (cd vault && python3 -m pytest tests/ -q) => 106 passed.
- python3 -m pytest tests/ -q --cov=scripts --cov-fail-under=80 => 694 passed, scripts coverage 91.50%.
- python3 -m mypy => Success: no issues found in 51 source files.
- python3 -m ruff check scripts/ tests/ hooks/ vault/ => All checks passed.
- bash scripts/quality/check-module-size.sh => OK.
- python3 scripts/docs/check_doc_reference_integrity.py => OK.

Carried-forward evidence still valid:
- hook selftests 13/13, 9/9, 9/9 passed; bats 40/40 and 47/47 passed; Graphify query suite passed 27/27 after Wave 9 graphify update.
- strict vault mypy pilots=16.
- CI coverage floor raised 75 -> 80.

Scoring dimensions and weights: type_safety .09, test_quality .13, error_handling .10, code_structure .09, configuration .07, logging .09, async_correctness .10, documentation .07, security .07, architecture .05, performance_budget .06, llm_prompt_quality .05, ci_cd_quality .03.

Output concise markdown with a JSON score block and adversarial notes. Score must be evidence-backed and conservative. If below 90, say so plainly.
