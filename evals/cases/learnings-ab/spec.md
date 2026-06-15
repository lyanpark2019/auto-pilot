# Learnings gate A/B — outcome-level eval

**Status**: DEFERRED
**Reason**: requires real Claude budget + a curated corpus of tickets relevant to
the target spec + ideally tickets that have accumulated across multiple real loop runs.
A fake fixture corpus (as used in the unit tests) cannot prove the gate improves
pass-rate — only real loop outcomes can.

## Goal

Quantify whether gate-filtered learnings injection improves loop outcomes (pass-rate,
iterations-to-green, token cost) vs no injection.

## Setup

1. Seed the home ledger with a curated set of tickets relevant to the target spec.
2. Run `auto-pilot start --spec <target-spec>` twice against an identical repo state:
   - **arm A** (injected): normal run — gate selects tickets, `resolve_learnings` injects.
   - **arm B** (no-inject): same run with `AUTO_PILOT_DISABLE_LEARNINGS=1` — injection skipped.
3. Both runs use the same model, same spec, same max-workers.

## Oracle

Defined in `oracle.py` (stub — fill in when the eval runs):

- `pass_rate`: fraction of phases that pass review in round 1.
- `iters_to_green`: median review rounds before APPROVE.
- `token_cost`: total tokens across both reviewers.

Arm A wins if `pass_rate_A > pass_rate_B` at p < 0.05 (Fisher's exact) over ≥10 runs.

## Toggle

`AUTO_PILOT_DISABLE_LEARNINGS=1` → `resolve_learnings` returns `None` (no file written,
no learnings in context bundle).  See `scripts/_learnings.py:resolve_learnings`.

## What the unit tests already cover

`tests/test_measure_learnings_injection.py::test_compare_gating_*` confirm that the
gate filters out sub-threshold and excluded-state tickets at the measurement layer.
This eval tests whether those filtered tickets actually degrade or improve outcomes.

## Why deferred

- Each arm needs ≥10 independent runs to reach statistical significance.
- Curating a relevant ticket corpus requires a real project with real loop history.
- Real Claude API budget is needed for each run.
- Scheduling: blocked until a stable project with ≥20 gate-passed tickets is available.
