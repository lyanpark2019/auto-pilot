All evidence verified. Here's the adversarial rescore.

---

## Adversarial Rescore — auto-pilot v0.8.7, Wave 8 (HEAD = 8eca25d)

### Dimension Scores

```json
{
  "evaluator": "claude-adversarial-wave8-rescore",
  "head_sha": "8eca25d",
  "baseline": "v0.8.6 = 84.40",
  "prior_wave7": 84.45,
  "dimensions": {
    "type_safety":        {"score": 88, "weight": 0.09, "weighted": 7.92},
    "test_quality":       {"score": 88, "weight": 0.13, "weighted": 11.44},
    "error_handling":     {"score": 90, "weight": 0.10, "weighted": 9.00},
    "code_structure":     {"score": 91, "weight": 0.09, "weighted": 8.19},
    "configuration":      {"score": 88, "weight": 0.07, "weighted": 6.16},
    "logging":            {"score": 89, "weight": 0.09, "weighted": 8.01},
    "async_correctness":  {"score": 91, "weight": 0.10, "weighted": 9.10},
    "documentation":      {"score": 88, "weight": 0.07, "weighted": 6.16},
    "security":           {"score": 89, "weight": 0.07, "weighted": 6.23},
    "architecture":       {"score": 84, "weight": 0.05, "weighted": 4.20},
    "performance_budget": {"score": 86, "weight": 0.06, "weighted": 5.16},
    "llm_prompt_quality": {"score": 86, "weight": 0.05, "weighted": 4.30},
    "ci_cd_quality":      {"score": 90, "weight": 0.03, "weighted": 2.70}
  },
  "weighted_total": 88.57,
  "verdict": "BELOW_90"
}
```

### Adversarial Notes per Dimension

**Type Safety (88).** 327 typed args vs 1 untyped — excellent. mypy strict on 51 files passes. Dinged from 90+ because `dict[str, Any]` appears 23 times in `_contract.py`/`_dispatch.py` as the primary contract/ticket data structure — no TypedDict or dataclass for these core domain objects. Protocol usage exists (`SpawnHandleProtocol`) but is isolated to one module. Rubric says 85-94 for "well-typed, small Any in infra"; this sits mid-band since `Any` is in domain-adjacent dispatch, not pure infra.

**Test Quality (88).** 665 root + 106 vault = 771 tests. 34 parametrize markers (claimed 18, actual 34 — undercounted, positive surprise). Coverage 91.63% with CI floor at 80. headless-loop 97%, risk_assess 97% — both up from well below. Dinged from 90+ because: (a) no property-based testing (Hypothesis/proptest), (b) integration test boundary (live claude subprocess) is mocked only — acceptable but rubric "90-100" wants error path + boundary + parametrize + high coverage; property tests would cross that line.

**Error Handling (90).** Zero broad `except Exception`, zero bare `except:`. Production code uses narrowed catches (`subprocess.TimeoutExpired`, `OSError`, `CalledProcessError`, `json.JSONDecodeError`). Log redaction strips secrets before they hit stderr. Rubric 90-100 threshold met.

**Code Structure (91).** `long_functions_gt40=0`. All files ≤500 lines (max 442 for `orchestrator.py`). CI gate enforces module size. Clean early-return patterns observed.

**Configuration (88).** `docs/configuration.md` has env var / default / bounds / consumer matrix. `tests/test_config.py` has 10 test functions guarding all numeric bounds + env overrides + doc drift. Dataclass with `__post_init__` validation, frozen where appropriate. Dinged from 90+ because: no pydantic `Settings`/`Field` — uses vanilla dataclass; rubric explicitly checks for `pydantic Settings/Field` + `@field_validator`. Functional but not rubric-ideal.

**Logging (89).** 46 production `event()` call sites across 10+ modules + 1 in `_log.py` itself = 47 (metric says 55 — likely includes vault). Structured `key=value` format. Secret redaction verified in code and test. `print_calls=0`. Dinged from 90 because: no explicit latency/timing fields on subprocess calls (event log captures event name + error, but no `duration_ms=` on external calls). Rubric wants "외부 API 호출 전후 로그 (latency 포함)".

**Async/Subprocess Correctness (91).** `subprocess_without_timeout=0`, `shell_true_calls=0`. All `subprocess.run`/`check_output` have explicit timeouts verified in `_dispatch.py` (line 139, 283), `_budget.py`, `_dogfood_gate.py`. Reviewer wrapper has soft+hard timeout with kill grace. No blocking I/O in async paths (codebase is sync/subprocess, not asyncio — correct for CLI orchestrator).

**Documentation (88).** Public API docstring coverage 263/265 = 99.25% — huge lift from 48.7%. Only 2 intentional misses in a 499-line file. `docs/configuration.md`, `docs/perf-budget.md`, `docs/architecture.md` all present and tested for drift. Dinged from 90+ because: docstrings exist but many lack full `Args/Returns/Raises` structure — rubric 88-100 explicitly asks for those fields. Coverage is quantity, not depth.

**Security (89).** Log redaction for `api_key/token/password/secret/credential/authorization/auth` keys + `Bearer`/`sk-*`/`gh*_*` value patterns — tested. CI has `pip-audit` + `gitleaks` jobs — test-guarded. No SQL, no user-facing HTTP surface. Dinged from 90+ because: path traversal guards are implicit (all paths from config/env, not user HTTP input), but no explicit `os.path.realpath` / `pathlib.resolve` assertions at trust boundaries.

**Architecture (84).** Clean module separation: `_state`, `_config`, `_log`, `_contract`, `_dispatch`, `_budget`, `_worktree` etc. One Protocol (`SpawnHandleProtocol`). Frozen dataclasses for config/contracts. Dinged because: (a) no DI container or bootstrap entry point — modules import each other directly, (b) `_dispatch.py` at 440 lines does ticket prep + diff freeze + round collection + marker wait + review read — multiple responsibilities. Rubric 81-91 for "good DI, small coupling"; sits at lower end.

**Performance Budget (86).** 4 benchmarks with absolute 50ms budget + committed regression baseline. `perf_baseline.json` has all 4 entries. `docs/perf-budget.md` documents refresh procedure. CI gate guards perf job existence. Dinged from 90+ because: (a) no RSS/memory ceiling measurement, (b) no p50/p95/p99 latency distribution — only mean, (c) rubric 92-100 wants "latency/memory/throughput SLO + CI gate + regression alarm"; memory and throughput are absent.

**LLM Prompt Quality (86).** 20 regression fixtures in `prompts/fixtures/`. Test enforces >=20 count + rendering correctness. Prompts in `.md` files, not inline strings. Dinged from 90+ because: (a) no structured output schema validation (pydantic Response model / JSON Schema enforcement on LLM output), (b) no adversarial fixtures, (c) rubric 90-100 wants "prompt version management + regression suite + structured output schema + drift alarm".

**CI/CD Quality (90).** CI has: mypy strict, ruff, pytest with `--cov-fail-under=80`, pip-audit, gitleaks, perf benchmark, module-size gate, doc-reference integrity. All enforced (not advisory). Test file guards CI job existence. Meets rubric 90-100 threshold.

### Summary

| Wave | Score |
|------|-------|
| v0.8.6 baseline | 84.40 |
| Wave 7 | 84.45 |
| **Wave 8** | **88.57** |

**+4.12 from Wave 7.** Lift is earned — docstring coverage jump (48.7%→99.25%), headless-loop/risk_assess coverage (54→97%, 75→97%), secret redaction, perf baseline expansion, config documentation are all verified in code. No inflation detected.

**Below 90.** Remaining gaps: `dict[str, Any]` in domain types (type_safety), no pydantic Settings (configuration), no latency-annotated logs (logging), `_dispatch.py` multi-responsibility (architecture), no memory/p99 perf budgets (performance), no structured output schema on LLM responses (llm_prompt_quality). Each is a real rubric miss, not a nitpick.
