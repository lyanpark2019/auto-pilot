# Evals harness (cut 1 — advisory)

Cut 1 proves the clone→init→loop→oracle plumbing and the deterministic stats.
It does **not** arm a blocking gate (1 case × K=5 = 5 attempts < the 50 arming
floor; baseline is hand-written). The rate gate arms in cut 2 on a measured baseline.

## Unit gate (per-PR, no agent runs)
`python3 -m pytest tests/test_evals_*.py -q` — runs in CI's python gate.

## Manual end-to-end smoke (one real agent run; costs ~$1-5, minutes)
Run in a **clean window** — no other `claude` sessions active. The eval disables
the per-loop fork-bomb pid guard, but a real agent still runs. The eval CLI exposes
only `--max-total-cost-usd` (whole-run ceiling, default $50; stops before the next
case once exceeded). The per-case ceiling is not a CLI flag in cut 1 — it is fixed
at $5 in `run_case` (scripts/evals/runner.py:76) and forwarded to the internal
`headless-loop.py --max-cost-usd` (runner.py:53).
```
python3 scripts/evals/cli.py run --case dogfood-smoke --repeats 1
```
Expect: `dogfood-smoke: 1/1 pass (advisory armed=False ...)`. This clones the
repo, runs auto-pilot headless on the dogfood spec, and asserts the deliverable.

## Layers
- Gate 1 (this): task-success rate — advisory in cut 1.
- Gate 2 (unchanged): `scripts/dogfood_tier1.sh` — harness-health, still blocking.
