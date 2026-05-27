# auto-pilot performance budget

Targets for the orchestrator CLI helper. Measured with `pytest-benchmark` on
local dev hardware (Apple M-series, Python 3.13).

## Budgets

| Operation | Budget | Rationale |
|---|---|---|
| `orchestrator status` | < 50 ms | called every loop iteration; user-visible |
| `orchestrator phase-start` | < 50 ms | called once per phase transition |
| `orchestrator phase-end` | < 50 ms | same |
| `orchestrator pivot-check` | < 50 ms | called per finding within a round |
| pytest suite (`tests/`) | < 5 s | dev feedback loop |

## How budgets are enforced

`tests/test_perf.py` runs each command under `pytest-benchmark` and asserts
`stats["mean"] * 1000 < 50.0`. Run locally with:

```
pytest tests/test_perf.py --benchmark-only -v
```

If the assertion fails, either:
- Inspect the regression with `--benchmark-compare` (requires a prior baseline run).
- Tune the implementation (avoid re-reading state files, drop redundant JSON
  encodes in tight loops).
- Re-evaluate the budget if the operation is no longer in a hot loop.

## Baseline regression

In addition to the 50 ms ceiling, each `test_*_within_budget` test asserts the
measured mean is `<=` a committed baseline (`tests/perf_baseline.json`). The
baseline values are set to **1.5× the measured mean** on dev hardware — wide
enough to absorb normal noise, tight enough to catch a genuine 50%+ regression
before it lands on `main`.

Refresh procedure after an intentional perf-affecting change:

```
python3 -m pytest tests/test_perf.py --benchmark-only --benchmark-json=/tmp/perf-new.json
python3 -c "
import json
data = json.load(open('/tmp/perf-new.json'))
for b in data['benchmarks']:
    print(b['fullname'], '->', b['stats']['mean'] * 1.5)
"
# manually update tests/perf_baseline.json with the new 1.5x values
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
