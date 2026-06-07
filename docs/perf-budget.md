---
type: runbook
topic: auto-pilot-performance-budget
source_commit: bbb06bfcbc54712b1ffff46673d3cfd112bc3ecb
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

## How budgets are enforced

`tests/test_perf.py` runs each command under `pytest-benchmark` and asserts
`stats["mean"] * 1000 < 50.0`. Run locally with:

```
pytest tests/test_perf.py --benchmark-only -v
```

The `test_rss_under_ceiling` test (non-benchmark) checks peak RSS of the
`risk_assess.assess` hot path after a representative call sequence. It runs
with the normal `pytest tests/ -q` invocation (not `--benchmark-only`).

The pytest suite takes tens of seconds locally on an M-series Mac, including
benchmark overhead. The `< 5 s` target in earlier versions was aspirational and
unmeasured. Do not duplicate collected test counts or wall-time ceilings here —
pytest output and CI duration are the SoT. No automated session-duration gate is
in-tree; the benchmark assertions (`<50 ms` absolute, `<=baseline` regression)
are the primary latency guards. Suite wall-time is monitored informally via CI
duration.

If the assertion fails, either:
- Inspect the regression with `--benchmark-compare` (requires a prior baseline run).
- Tune the implementation (avoid re-reading state files, drop redundant JSON
  encodes in tight loops).
- Re-evaluate the budget if the operation is no longer in a hot loop.

## Baseline regression

In addition to the 50 ms ceiling, each `test_*_within_budget` test asserts the
measured mean is `<=` a committed baseline (`tests/perf_baseline.json`). The
absolute budget (`<50 ms`) is the primary gate; this baseline assertion is the
secondary smoke catching catastrophic regressions.

Baseline values are sized to tolerate shared-runner variance:
- Local M-series Mac, Python 3.13: ~500 µs measured mean per command.
- GitHub Actions `ubuntu-latest`, Python 3.13: 0.5–11 ms observed range
  across runs (CI hardware is a noisy neighbour environment; 10× spread is
  not unusual).

Each baseline is set at **25 ms**, well below the 50 ms absolute budget but
loose enough to never flake on a slow CI runner. The gate triggers on a
genuine ≥25× slowdown vs local — caught regressions are catastrophic, not
incremental. For finer-grained regression tracking, switch to
`pytest-benchmark --benchmark-compare-fail` with a maintained `.benchmarks/`
history (deliberately out of scope for this plugin).

Refresh procedure after an intentional perf-affecting change:

```
python3 -m pytest tests/test_perf.py --benchmark-only --benchmark-json=/tmp/perf-new.json
python3 -c "
import json
data = json.load(open('/tmp/perf-new.json'))
for b in data['benchmarks']:
    print(b['fullname'], '->', b['stats']['mean'] * 25)
"
# update tests/perf_baseline.json with the new 25x values (round up)
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
