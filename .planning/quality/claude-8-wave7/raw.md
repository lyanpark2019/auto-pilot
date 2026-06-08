Enough evidence collected. Scoring now.

---

# Adversarial Rescore — auto-pilot v0.8.7 (Wave 7)

**HEAD:** `1046c8a` | **Evaluator:** independent adversarial | **Date:** 2026-06-08
**Baseline:** v0.8.6 = 84.40/100

## Dimension Scores

| # | Dimension | Wt | Score | Evidence / Deductions |
|---|---|---|---|---|
| 1 | type_safety | .09 | **85** | mypy --strict passes 51 files (up from 2). Protocol DI in `_reviewer_wrapper`. But: 60 `Any` refs across 29 prod files, `ignore_missing_imports=True` weakens strict, heavy `dict[str, Any]` for JSON payloads instead of TypedDict. |
| 2 | test_quality | .13 | **83** | 622+106+87 bats+31 hook = 846 tests. Coverage 87.80% (gate 80%). 11 parametrize markers (was 6). Benchmark + prompt regression. **Drag:** headless-loop.py 54% cov, risk_assess.py 75%. No property-based tests. Parametrization ratio still low (11/622). |
| 3 | error_handling | .10 | **87** | broad_exceptions=0, bare except=0, 55 event() calls (was 37). `from e` chaining in narrowed handlers. **Drag:** 55 events across 29 files ≈ 1.9/file — some error paths lack structured logging. |
| 4 | code_structure | .09 | **91** | long_functions_gt40=0 (was 34). Module size gate ≤500 lines CI-enforced. Clean extraction in wave 5-6 across dispatch, worktree, reviewer wrapper, source adapter. |
| 5 | configuration | .07 | **82** | `AutoPilotConfig` dataclass with env-driven defaults. `PREFLIGHT_TTL_SEC` configurable. **Drag:** no pydantic `Field(ge=..., le=...)` validation, no formal env-var docs, no dev/staging/prod separation. |
| 6 | logging | .09 | **84** | print_calls=0 (was 168). 55 structured `event()` calls. Error events carry `error_type=`, `reason=`. **Drag:** no correlation ID, no external call latency logging, moderate event density. |
| 7 | async_correctness | .10 | **88** | subprocess_without_timeout=0, shell_true_calls=0. Worktree module has budgeted `_GIT_QUICK_TIMEOUT`/`_GIT_TREE_TIMEOUT`. headless-loop `_timed_stream` wraps Popen. Sync codebase — scored on subprocess discipline. |
| 8 | documentation | .07 | **76** | 106/156 public APIs documented (67.9%). CLAUDE.md comprehensive. doc-citation-integrity passes. design_doc_freshness: 0 STALE. **Drag:** 50 public APIs missing docstrings — below rubric 79+ tier. |
| 9 | security | .07 | **86** | shell=True=0. JSON schema validation on contracts/tickets/reviews. Env denylist in reviewer_wrapper. 7+ guard hooks (reviewer-write, destructive, deletion-diff, gh-auth). **Drag:** no pip-audit/SBOM in CI, no explicit secret redaction in event() output. |
| 10 | architecture | .05 | **84** | Protocol DI (SpawnHandleProtocol). 13 clean helper modules with single responsibility. No circular imports (mypy would catch). **Drag:** only 1 Protocol type. No formal bootstrap/DI container. orchestrator.py has direct multi-module coupling. |
| 11 | performance_budget | .06 | **81** | 4 pytest-benchmark tests in CI. Absolute ceiling (50ms) + RSS ceiling (200MB). `perf_baseline.json` committed. **Drag:** no `--benchmark-compare-fail` regression gate. Only 4 benchmarks. No p50/p95 formal SLO doc. |
| 12 | llm_prompt_quality | .05 | **82** | Prompts in `prompts/*.md` (separated). 10 regression fixtures. `scripts/evals/` harness (runner, oracle, aggregate, regress). JSON schemas for structured output. **Drag:** 10 fixtures < rubric's 20+ target. No PII/secret output sanitizer. No model upgrade diff gate. |
| 13 | ci_cd_quality | .03 | **84** | 3 CI jobs (python/bash/bats), 7+ enforced gates, timeout-minutes ≤5. Coverage floor 80%. Shellcheck pinned. Doc-citation + module-size in CI. **Drag:** no dep audit, no SBOM, no secret-leak scan, benchmark runs but doesn't gate on regression. |

## Score Calculation

```json
{
  "version": "v0.8.7-wave7",
  "head": "1046c8a",
  "baseline": 84.40,
  "dimensions": {
    "type_safety":        {"weight": 0.09, "score": 85, "weighted": 7.65},
    "test_quality":       {"weight": 0.13, "score": 83, "weighted": 10.79},
    "error_handling":     {"weight": 0.10, "score": 87, "weighted": 8.70},
    "code_structure":     {"weight": 0.09, "score": 91, "weighted": 8.19},
    "configuration":      {"weight": 0.07, "score": 82, "weighted": 5.74},
    "logging":            {"weight": 0.09, "score": 84, "weighted": 7.56},
    "async_correctness":  {"weight": 0.10, "score": 88, "weighted": 8.80},
    "documentation":      {"weight": 0.07, "score": 76, "weighted": 5.32},
    "security":           {"weight": 0.07, "score": 86, "weighted": 6.02},
    "architecture":       {"weight": 0.05, "score": 84, "weighted": 4.20},
    "performance_budget": {"weight": 0.06, "score": 81, "weighted": 4.86},
    "llm_prompt_quality": {"weight": 0.05, "score": 82, "weighted": 4.10},
    "ci_cd_quality":      {"weight": 0.03, "score": 84, "weighted": 2.52}
  },
  "total_weighted": 84.45,
  "verdict": "BELOW_90"
}
```

**Weighted total: 84.45 / 100 — below 90.**

## Adversarial Notes

1. **v0.8.6 baseline was likely inflated.** Wave 5-7 zeroed out long_functions (34→0), broad_exceptions (30→0), print_calls (168→0), raised coverage 80→88%, expanded mypy strict 2→51 files — yet the total barely moved (+0.05). This means the prior 84.40 was scored generously relative to the rubric. My score reflects the actual current state against rubric criteria.

2. **Documentation is the biggest drag.** 67.9% public API docstring coverage caps dim 8 at 76. This dimension alone costs ~0.84 weighted points vs an 88 score. Adding docstrings to 50 public functions is the highest-ROI improvement.

3. **Test quality ceiling:** headless-loop.py (54% cov) is a critical driver module. risk_assess.py (75%) is below the 80% floor. 11 parametrize markers in 622 tests shows low test-design maturity. To reach 90+ on this dim: cover headless-loop error paths, add parametrize to at least 20+ test functions, consider property-based testing.

4. **No path to 90 without multi-dimension lifts.** Reaching 90.0 requires ~5.55 weighted points. Minimum viable path:
   - documentation 76→88 (+0.84)
   - test_quality 83→90 (+0.91)
   - configuration 82→90 (+0.56)
   - logging 84→90 (+0.54)
   - performance_budget 81→88 (+0.42)
   - type_safety 85→90 (+0.45)
   - llm_prompt_quality 82→88 (+0.30)
   - Total potential: +4.02 → 88.47 (still short). Need deeper work on high-weight dims or near-perfection on several.

5. **Inflation guard:** code_structure at 91 is the only dim above 90. Justified by hard metric (zero long functions + CI module-size gate). No other dim has evidence supporting 90+.
