---
type: runbook
topic: auto-pilot-performance-budget
source_commit: 52776f7440fe2dd2bf472784717549be258b7c75
manual_edit: false
---

# auto-pilot performance budget

Targets for the orchestrator CLI helper. Measured with `pytest-benchmark` on
local dev hardware (Apple M-series, Python 3.13).

## Budgets

| Operation | Budget | Rationale |
|---|---|---|
| `orchestrator status` | < 50 ms | called every loop iteration; user-visible |
| `orchestrator phase-start` | < 50 ms | called once per phase transition |
| `orchestrator phase-end` | < 50 ms | same |
| `orchestrator pivot-check` (`risk_assess.assess`) | < 50 ms | called per finding within a round; measured ~0.03 ms locally |
| pytest suite (`tests/`) | informally monitored | no in-tree wall-time gate; pytest output and CI duration are the live SoT |
| peak RSS (assess 200 paths × 50 runs) | < 200 MB | `test_rss_under_ceiling` in `tests/test_perf.py` |
| CLI import cold start | < 2 s | `test_cli_import_cold_start_under_budget` in `tests/test_perf.py` |

## How budgets are enforced

`tests/test_perf.py` runs each command under `pytest-benchmark` and asserts
`stats["mean"] * 1000 < 50.0`; when sample data is available it also asserts
p95 sample latency stays below 50 ms. Run locally with:

```
pytest tests/test_perf.py --benchmark-only -v
```

The `test_rss_under_ceiling` test (non-benchmark) checks peak RSS of the
`risk_assess.assess` hot path after a representative call sequence. The
`test_cli_import_cold_start_under_budget` test measures a fresh Python process
importing the CLI hot modules. CI runs both explicitly beside the normal
`pytest tests/ -q` coverage run.

The pytest suite takes tens of seconds locally on an M-series Mac, including
benchmark overhead. The `< 5 s` target in earlier versions was aspirational and
unmeasured. Do not duplicate collected test counts or wall-time ceilings here —
pytest output and CI duration are the SoT. No automated session-duration gate is
in-tree; the benchmark assertions (`<50 ms` mean/p95, `<=baseline` regression),
RSS ceiling, and cold-start ceiling are the primary perf guards. Suite wall-time
is monitored informally via CI duration.

If the assertion fails, either:
- Inspect the regression with `--benchmark-compare` (requires a prior baseline run).
- Tune the implementation (avoid re-reading state files, drop redundant JSON
  encodes in tight loops).
- Re-evaluate the budget if the operation is no longer in a hot loop.

## Baseline regression

In addition to the 50 ms ceiling, each `test_*_within_budget` test asserts the
measured mean is `<= baseline * BASELINE_TOLERANCE` (where `BASELINE_TOLERANCE = 1.25`
in `tests/test_perf.py`). The absolute mean/p95 budget (`<50 ms`) is the primary gate;
this baseline assertion is the secondary smoke catching catastrophic regressions.

Baselines are per-test measured ceilings (not a uniform placeholder):

| Test | Local mean (M-series, Py 3.13) | Committed baseline | Headroom |
|---|---|---|---|
| `test_status_within_budget` | ~1.2 ms | 0.012 s (12 ms) | ~10× local |
| `test_phase_start_within_budget` | ~1.4 ms | 0.012 s (12 ms) | ~8.6× local |
| `test_phase_end_within_budget` | ~9.8 ms | 0.025 s (25 ms) | ~2.6× local |
| `test_pivot_check_within_budget` | ~0.037 ms | 0.0015 s (1.5 ms) | ~40× local |

With `BASELINE_TOLERANCE = 1.25`, the effective regression ceiling is
`baseline × 1.25` per test (e.g. phase-end limit = 31.25 ms, still well under
50 ms absolute budget). GitHub Actions `ubuntu-latest`, Python 3.13 shows a
0.5–11 ms observed range across runs (CI hardware is a noisy-neighbour
environment; 10× spread is not unusual). The per-test baselines are sized to
absorb that variance without flaking.

CI flake risk: status/phase-start baselines (12 ms ceiling × 1.25 = 15 ms
effective) have ~10× headroom over local mean; should never flake even on a
slow runner. phase-end (25 ms × 1.25 = 31.25 ms) has ~2.6× headroom — CI has
shown up to 11 ms observed; if a slow runner or extra I/O adds latency, raise
the phase-end baseline to 0.030 before any CI flake occurs. pivot-check is
pure CPU and CI-stable at any reasonable load.

Refresh procedure after an intentional perf-affecting change:

```
python3 -m pytest tests/test_perf.py --benchmark-only --benchmark-json=/tmp/perf-new.json
python3 -c "
import json
data = json.load(open('/tmp/perf-new.json'))
for b in data['benchmarks']:
    print(b['fullname'].split('::')[-1], '->', round(b['stats']['mean'] * 1000, 3), 'ms')
"
# Set each tests/perf_baseline.json stats.mean to a clean ceiling at or above the
# measured mean (round up; add CI headroom for light CLI commands; keep phase-end's
# larger ceiling to account for real evidence-gate I/O). BASELINE_TOLERANCE stays 1.25.
git add tests/perf_baseline.json && git commit -m "perf(baseline): refresh after intentional change"
```

Note: full pytest-benchmark `--benchmark-compare` would require a maintained
`.benchmarks/` history directory, which we don't keep in the repo. The
committed-JSON approach gives us a regression gate without that overhead.

## Out of scope

- `headless-loop.py` is intentionally bounded by `--timeout-build` (default
  4 h) and not subject to a per-call latency budget — it's a long-running
  orchestrator, not a CLI.
- Hook scripts (`hooks/*.sh`) are gated by Claude Code's hook timeout and
  measured indirectly through the pytest hook suite (subprocess overhead
  dominates).
