Now have full evidence. Scoring each dimension.

---

# v0.8.7 Adversarial Rescore — HEAD `403283e`

## Methodology

Independent verification of claimed metrics, rubric-aligned scoring, conservative.
Metric snapshot scope: `scripts/`, `hooks/`, `vault/` (excludes `codex/`, `tests/` dirs).
Actual codebase-wide long functions: **32** (including `codex/` and tests). Metric scope: **11** in `scripts/hooks/vault` prod code — **verified correct** for that scope.

## Per-Dimension Scores

```json
{
  "version": "v0.8.7",
  "head": "403283e",
  "baseline": "v0.8.6 @ 84.40",
  "dimensions": {
    "type_safety":        { "score": 82, "weight": 0.09 },
    "test_quality":       { "score": 84, "weight": 0.13 },
    "error_handling":     { "score": 83, "weight": 0.10 },
    "code_structure":     { "score": 85, "weight": 0.09 },
    "configuration":      { "score": 81, "weight": 0.07 },
    "logging":            { "score": 84, "weight": 0.09 },
    "async_correctness":  { "score": 78, "weight": 0.10 },
    "documentation":      { "score": 79, "weight": 0.07 },
    "security":           { "score": 86, "weight": 0.07 },
    "architecture":       { "score": 84, "weight": 0.05 },
    "performance_budget": { "score": 83, "weight": 0.06 },
    "llm_prompt_quality": { "score": 85, "weight": 0.05 },
    "ci_cd_quality":      { "score": 84, "weight": 0.03 }
  },
  "weighted_total": 82.52,
  "verdict": "BELOW 90 — does not meet target"
}
```

## Dimension Rationale

### type_safety: 82
- mypy `--strict` passes for 49 source files — real improvement from 2-file pilot.
- But `Any` imported in **20 production files**. `ignore_missing_imports = True` masks real type gaps.
- No Protocol/ABC usage outside `_reviewer_wrapper.py` and `vault/sources/_adapter.py` — most modules use concrete coupling.
- Score 82 = "well typed with non-trivial Any in domain" (rubric 75-84 band, upper end).

### test_quality: 84
- 611 root + 106 vault = 717 total tests, 66 test files, 106 error-path assertions. Solid count.
- Scripts coverage 87.50% (CI gate only 75% — gap between local and CI floor is risky, someone could regress to 76% and pass).
- Only **9** parametrize markers across 717 tests — rubric expects parametrized boundary cases for 90+.
- Zero `@pytest.mark.integration` tests — all tests are unit. No integration-level subprocess/end-to-end validation in CI.
- Only 1 eval case in `evals/cases/` — thin eval harness.
- Score 84 = "good coverage, some parametrization" (rubric 80-89 band, mid-range).

### error_handling: 83
- **8 broad `except Exception`** remaining (down from 30, real progress).
- Structured `event()` calls up to 56, but 37 raw `print()` calls remain in production code (scripts/_contract, _dispatch, _log, build_dashboard, docs checks).
- No `raise ... from e` chaining patterns observed.
- `_log.py:13` has `print()` in the logging module itself — should use its own structured output.
- Score 83 = "mostly explicit, small gaps" (rubric 80-89 band, lower).

### code_structure: 85
- Long functions >40 lines: **11** in metric scope (verified). Real improvement from 34.
- Largest: `prepare_subagent_ticket` at 69 lines, `reap_orphans` 56, `bootstrap` 56. Meaningful splits remain.
- Module-size gate passes (all ≤500 lines).
- Early return patterns used in some modules but not consistently.
- Score 85 = "small number of violations, one complex function" (rubric 82-89).

### configuration: 81
- `AutoPilotConfig` dataclass with env-driven defaults exists.
- `_GIT_QUICK_TIMEOUT` / `_GIT_TREE_TIMEOUT` constants in `_worktree.py` — not externalized.
- Magic numbers in several places (budget caps, thresholds scattered across modules).
- No pydantic `Settings` / `Field` validators. Config is a plain dataclass.
- Score 81 = "mostly managed, some magic numbers" (rubric 80-87 lower).

### logging: 84
- `event()` calls increased 37→56, covering more hot paths.
- Still **37 raw print()** in production code that bypass structured logging.
- Error logs not consistently using `error_type=` field pattern.
- Score 84 = "mostly structured, some gaps" (rubric 80-89).

### async_correctness: 78
- **44 subprocess calls without explicit `timeout` parameter** across `scripts/` and `vault/`. Key offenders:
  - `_worktree.py`: 14 calls — some use `_GIT_QUICK_TIMEOUT` but many don't show `timeout` on the subprocess line itself (verified: the module does define timeout constants, but my grep showed 14 NO-TIMEOUT hits).
  - `_dispatch.py`: 3 calls without timeout.
  - `build_dashboard_data.py`: 2 git calls, no timeout.
  - `_reviewer_wrapper.py`: 4 calls without timeout (the module implements watchdog timeouts at a higher level, but individual subprocess calls lack protection).
- `evals/oracle_api.py` uses `shell=True` — mitigated by controlled `cmd` from config and constrained PATH, but still a risk signal.
- No async/await in the codebase (sync subprocess model), so async-specific issues don't apply. But the subprocess timeout gap is the primary async_correctness concern.
- Score 78 = "timeout missing on loops/calls, potential blocking" (rubric 71-79).

### documentation: 79
- 109 public functions, **34 missing docstrings (31%)** — rubric wants "most public API documented" for 80+.
- CLAUDE.md is well-maintained with layout table and test recipes.
- `docs/architecture.md` exists as canonical reference.
- doc-citation-integrity check passes (no dead `file:line` refs).
- Score 79 = "partial docstring" (rubric 70-78, pushed to top for good CLAUDE.md).

### security: 86
- Gitleaks secret scan in CI (SHA-pinned action — supply chain hardened).
- pip-audit CVE scan in CI.
- `shell=True` in `evals/oracle_api.py` only — controlled scope with restricted PATH.
- Path construction uses `Path()` consistently.
- No SQL, no user-facing API surface — plugin context limits attack surface.
- Score 86 = "keys redacted, small validation gap" (rubric 84-91).

### architecture: 84
- Protocol usage in `_reviewer_wrapper.py` (`SpawnHandleProtocol`) and `vault/sources/_adapter.py` (`SourceAdapter`).
- No circular imports detected.
- Clean module separation: `_state`, `_config`, `_log`, `_contract`, `_dispatch`, `_worktree`.
- No formal DI container — bootstrap paths are direct imports.
- Score 84 = "good DI, small coupling" (rubric 81-91, lower).

### performance_budget: 83
- `test_perf.py` with benchmark baselines + RSS ceiling — real perf gate in CI.
- `--benchmark-compare-fail` not wired (just `--benchmark-only` in CI).
- `perf_baseline.json` committed with regression detection logic.
- No p95/p99 latency tracking, no async throughput measurement.
- Score 83 = "some SLO defined, some measurement gaps" (rubric 80-91).

### llm_prompt_quality: 85
- Prompts in files (`prompts/headless.md`, `prompts/iteration.md`), not inline strings.
- 20 regression fixtures with substring-match assertions (not brittle full-text).
- 4 JSON schemas in `schemas/` for contract/ticket/review/preflight.
- Only 1 eval case — thin adversarial coverage.
- No prompt-level PII sanitizer.
- Score 85 = "regression baseline exists, prompt schema partial" (rubric 80-89).

### ci_cd_quality: 84
- CI gates: ruff, mypy --strict, pytest + coverage (75% floor), shellcheck (pinned 0.11.0), pip-audit, gitleaks, perf benchmark, doc-reference integrity. Comprehensive gate set.
- Missing: SBOM generation, integration test collection, `--cov-fail-under=80` (CI uses 75 while local achieves 87.5 — gap allows regression).
- Timeout-minutes set (5min for Python, 2min for bash, 3min for secret scan) — fast feedback.
- Score 84 = "core gates enforced, some advisory" (rubric 80-89).

## Weighted Calculation

| Dim | Score | Weight | Contribution |
|-----|-------|--------|-------------|
| type_safety | 82 | .09 | 7.38 |
| test_quality | 84 | .13 | 10.92 |
| error_handling | 83 | .10 | 8.30 |
| code_structure | 85 | .09 | 7.65 |
| configuration | 81 | .07 | 5.67 |
| logging | 84 | .09 | 7.56 |
| async_correctness | 78 | .10 | 7.80 |
| documentation | 79 | .07 | 5.53 |
| security | 86 | .07 | 6.02 |
| architecture | 84 | .05 | 4.20 |
| performance_budget | 83 | .06 | 4.98 |
| llm_prompt_quality | 85 | .05 | 4.25 |
| ci_cd_quality | 84 | .03 | 2.52 |
| **Total** | | **1.00** | **82.78** |

## Adversarial Notes

1. **Score does NOT reach 90.** Weighted total = **82.78**. Baseline was 84.40 — this is a marginal regression in weighted score despite genuine code improvements, because the rubric was applied more rigorously this round.

2. **Subprocess timeout gap is the largest drag.** 44 subprocess calls without explicit timeout across the codebase is a real async_correctness issue. `_worktree.py` alone has 14. Even if higher-level watchdogs exist, individual calls can hang indefinitely.

3. **Metric snapshot scope is honest but narrow.** Excluding `codex/` and test files is defensible (vendored fork, test code), but it hides 21 additional >40-line functions and significant `Any` usage in codex scripts. Evaluators should know this.

4. **Coverage gate gap.** CI enforces 75%, local measures 87.5%. This 12.5pp gap means someone could regress significantly and still pass CI. Should be ≥80% to match rubric expectations.

5. **Parametrize scarcity.** 9 markers across 717 tests — rubric 90+ needs "parametrized tests, boundary cases." Current test suite is predominantly single-assertion happy-path per test function.

6. **`Any` density in domain layer.** 20 files import `Any` from typing. With `ignore_missing_imports = True` in mypy.ini, strict mode is diluted — third-party stubs missing means type holes pass silently.

7. **37 raw print() in production code.** Structured event() improved but print-to-stdout remains in core modules (contract, dispatch, log module itself). The logging module printing is particularly anti-pattern.

8. **No integration tests tagged or collected.** Zero `@pytest.mark.integration` markers. The full loop (spec → init → dispatch → review → advance) has no automated end-to-end test.

## Delta from v0.8.6

Real improvements verified:
- Long functions: 34 → 11 (metric scope) — genuine
- Broad exceptions: 30 → 8 — genuine
- Print calls: 168 → 50 — genuine
- Coverage: 80.06% → 87.50% — genuine
- mypy scope: 2 → 14 strict files — genuine
- Test count: 595+91 → 611+106 — genuine

These are real quality lifts. But they don't cross the 90 threshold because the remaining gaps (subprocess timeouts, `Any` density, parametrize scarcity, docstring coverage, CI gate floor) each cap their respective dimensions below 85.

**Honest weighted score: 82.78.** Below 90. Below the 84.40 baseline when scored with this rubric application rigor. The code genuinely improved, but prior scoring was likely inflated.
