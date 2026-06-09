# Design — wire the Hermes miner live (Stop hook)

> Status: approved 2026-06-09. Follows the Hermes-loop MVP
> ([design](2026-06-09-hermes-loop-mvp-design.md) / [plan](2026-06-09-hermes-loop-mvp-plan.md))
> which shipped `learning_miner.py` but left it **inert** — nothing in the loop
> invoked it. This spec wires it to a trigger so cross-run accumulation happens.

## 1. Problem

`scripts/learning_miner.py` works in isolation (35 unit tests) but no part of the
auto-pilot loop runs it. Without an invocation point, the durable ledger never
accumulates across runs, so the `distinct_runs` gate can never flip
`thin → promotable`. The feature is dead until wired.

## 2. Decision — `Stop` hook (mechanism B2)

A new `Stop` hook fires the miner once per session, code-enforced. Chosen over:

- **PM phase-end Bash call (prose):** rejected — relies on the PM remembering a
  markdown step every run. Repo principle is "enforce with code, not prompts"
  (CLAUDE.md). A hook fires deterministically.
- **`SubagentStop` hook after reviewers:** rejected — the PM writes
  `critic-rejections-phase-N.jsonl` *after* the reviewer subagent returns, so a
  SubagentStop hook races the write and reads stale/missing data. It also fires
  per-subagent (dozens/phase) — noisy.
- **`/auto-pilot learn` subcommand:** dropped (YAGNI) — Task B's E2E test calls
  the CLI directly; no manual surface is needed yet.

**Why once-per-session is correct for the gate:** `_improvement._apply_bump`
dedups evidence on `(run_id, snippet)` and computes
`distinct_runs = len({e.run_id})` (`scripts/_improvement.py:188-194`). `run_id`
is constant within a run, so firing the miner once per session — or many times —
yields the same `distinct_runs`. The hook cannot inflate the gate.

## 3. Component — `hooks/learning-miner-stop.sh`

One unit, one purpose: on `Stop`, if this is an auto-pilot run, run the miner
advisory. Behavior, in order:

1. Read the Stop payload from stdin (JSON).
2. **Reentry guard** — `stop_hook_active == true` → exit 0 (copies
   `hooks/subagent-deliverable-check.sh`; prevents infinite Stop re-fire).
3. **Target root** — `${CLAUDE_PROJECT_DIR:-<payload cwd>:-$PWD}`. The env var is
   the repo's established pattern (`hooks/pm_final_report.sh:23`); payload `cwd`
   then `$PWD` are fallbacks. This is the repo being *driven* (the target), which
   in brownfield mode is **not** the plugin.
4. **Miner path** — the plugin's own copy, derived from the hook's location:
   `$(dirname "${BASH_SOURCE[0]}")/../scripts/learning_miner.py`. auto-pilot is a
   brownfield driver: when driving a target repo X, `learning_miner.py` lives in
   the plugin, not in X. Self-locating via `BASH_SOURCE` works for both the
   dogfood case (plugin == repo) and the brownfield case (plugin in cache dir).
   If the resolved miner path is missing → exit 0 (advisory).
5. **Activation guard** — if `<root>/.planning/auto-pilot/state.json` is absent
   → exit 0. Non-auto-pilot sessions no-op; the hook only acts on a real run.
6. Run `python3 "<miner>" --repo-root "<root>"` — no `--commit-to` (durable home
   ledger, never the target repo); no `--fail-on` (never blocks). stderr surfaces
   the verdict line to session output.
7. **Advisory** — exit 0 on every path, including miner error (`|| true`). The
   miner already wraps `bump_or_create` in try/except
   (`scripts/learning_miner.py:164`).

## 4. Data flow

```
session Stop
  → learning-miner-stop.sh (stdin JSON)
  → python3 <root>/scripts/learning_miner.py --repo-root <root>
  → run_miner: scan critic-rejections-phase-*.jsonl + state.json pivot_detector
  → bump_or_create per Observation (flock + atomic)
  → home ledger ~/.claude/projects/<slug>/improvements/<fp>.json
  → verdict JSON line → stderr
exit 0 (always)
```

## 5. Wiring

- Append a second entry to the `Stop` array in `hooks/hooks.json` (alongside
  `pm_final_report.sh`), matcher `*`.
- `chmod +x hooks/learning-miner-stop.sh`.

## 6. Testing

- **`hooks/test_learning_miner_stop.py`** — python self-test (subprocess +
  stdin, the `test_notebooklm_delete_gate.py` pattern). Cases:
  1. `stop_hook_active: true` → no-op, exit 0, miner not run.
  2. no `state.json` under cwd → no-op, exit 0.
  3. `state.json` present + a `critic-rejections-phase-1.jsonl` → miner runs,
     exit 0, a ticket file appears under a temp ledger (`--commit-to` via env, or
     assert stderr verdict). Use a `tmp` repo root + `HOME` override so the test
     never touches the real home ledger.
  4. garbage stdin → no-op, exit 0 (fail-open).
- Wire `python3 hooks/test_learning_miner_stop.py` into `ci.yml` after the
  existing hook self-tests (line 87).
- Existing 35 Python unit tests already cover `run_miner` internals.

## 7. Doc sync (same change)

- `CLAUDE.md:30` — add `learning-miner-stop.sh` to the hook list, bump
  `(20 scripts)` → `(21 scripts)`.
- `docs/architecture.md:128` — `(20 scripts` → `(21 scripts`.

## 8. Non-goals

No blocking, no `--commit-to` from the hook, no write into the target repo, no
phase-end prose change, no subcommand, no FSM/promotion changes (P2, deferred by
the MVP design §residual risk).

## 9. Residual risk

- **Home-ledger isolation in tests** — the self-test MUST override `HOME` (or use
  `--commit-to` a tmp dir) or it will write into the real durable ledger. Treated
  as a test-correctness blocker, not a runtime risk.
- **Multi-session runs** — a run that spans resume sessions fires the miner at
  each session Stop with the same `run_id`; idempotent, correct.
- **Stale state.json** — a leftover `state.json` from an old run makes the hook
  fire on an unrelated session. Harmless (advisory, idempotent), but noted.
