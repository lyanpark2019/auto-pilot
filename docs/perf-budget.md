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

## Out of scope

- `headless-loop.py` is intentionally bounded by `--timeout-build` (default
  4 h) and not subject to a per-call latency budget — it's a long-running
  orchestrator, not a CLI.
- Hook scripts (`hooks/*.sh`) are gated by Claude Code's hook timeout and
  measured indirectly through the pytest hook suite (subprocess overhead
  dominates).
