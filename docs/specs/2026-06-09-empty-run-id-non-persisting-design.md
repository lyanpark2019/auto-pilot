# Design — miner non-persisting scan on empty run identity

> Status: approved via grill (2026-06-09, brainstorming + grill-with-docs).
> Glossary: [`CONTEXT.md`](../../CONTEXT.md). Decision record:
> [`docs/adr/0001-empty-run-id-non-persisting.md`](../adr/0001-empty-run-id-non-persisting.md).
> This is also the **first real dogfood** of the auto-pilot loop — the deliverable
> is "the loop ran end-to-end on a real fix", the fix itself is intentionally small.

## 1. Problem (evidence-grounded)

The learning miner persists improvement tickets to the durable Ledger keyed by a
**run identity** (`run_id`). When `run_id` is empty — a standalone scan, a
stale/stub `state.json`, or any invocation outside an orchestrator-initialised
Run — the miner still writes tickets whose only evidence carries `run_id == ""`.

Two harms, both verified this session:

- **Permanent un-promotable clutter.** Such a ticket's `distinct_runs` is stuck
  at 1 (the empty string never varies), so it can never reach a promotion
  threshold; it is dead weight in the Ledger.
- **Phantom-run inflation (the worse one).** `distinct_runs = len({e["run_id"]
  for e in evidence})` (`scripts/_improvement.py`). The empty string counts as a
  *distinct run*. When a future **real** Run re-emits the same pattern (same
  fingerprint), it loads the polluted ticket and appends real evidence →
  `distinct_runs` jumps to 2 with only one real Run. The class then promotes
  after **2** real Runs instead of 3 — the `""` phantom silently shortcuts the
  gate by one Run.

Concrete residue: 4 polluted `insight` tickets (`fail-open`, `dead-path-doc`,
`reentry`, `shellcheck`) in the home Ledger, written by this session's standalone
validation pass.

## 2. Decision

**Miner-level guard, reusing the existing dry-run path.** When a Run has no run
identity, the miner performs a **non-persisting scan** (CONTEXT.md): it projects
tickets and emits a Verdict but writes nothing to the Ledger. We do **not**
synthesize a fallback `run_id` — see ADR 0001 for why (it re-imports the gaming
`distinct_runs` exists to prevent).

Locus chosen: the miner (`run_miner`), not the Stop hook — a single chokepoint
covers every caller (Stop hook **and** direct CLI; the validation pollution came
through the CLI path, which a hook-only guard misses).

## 3. Behaviour contract

- `run_miner` computes `effective_dry_run = dry_run or (not run_id)` and threads
  that into every `bump_or_create` call.
- On empty `run_id`: the report still shows `candidates = N` (the projected
  count of observations seen) and a Verdict computed from the projection;
  `0` tickets are persisted. A single structured `event(...)` line records
  `learning_miner.non_persisting` with the reason (empty run identity).
- On non-empty `run_id`: unchanged — tickets persist exactly as today.

## 4. Implementation scope

- `scripts/learning_miner.py` — `run_miner`: the `effective_dry_run` line + the
  `event(...)` log. No other behaviour change. (`--dry-run` flag semantics
  unchanged; this only *adds* an automatic trigger.)
- `tests/test_learning_miner.py` — new tests (§5).
- **No** change to `scripts/_improvement.py` (rejected option (b): self-healing
  evidence-drop would guard a state that is impossible once persistence is
  blocked — YAGNI).

## 5. Tests (TDD — RED first)

1. `test_empty_run_id_does_not_persist` — `state.json` with `run_id: ""` (and a
   variant with the key absent) + one `insights.jsonl` line; `run_miner(...,
   dry_run=False)` → **ledger dir has zero ticket files** and a Verdict is
   returned. (RED today: it writes a ticket.)
2. `test_empty_run_id_reports_projected_candidates` — same setup →
   `result["candidates"] == N` (projection visible, Q6 decision), not 0.
3. `test_nonempty_run_id_still_persists` — regression guard: `run_id: "r1"` →
   exactly one ticket file written (existing behaviour intact).
4. Existing `test_dry_run_verdict_matches_persist` stays green.

## 6. One-time cleanup (PM/operator, outside the worker diff)

Delete the 4 polluted ticket files (and their `.json.lock` sidecars) from
`~/.claude/projects/<slug>/improvements/`. Safe: they are known-bad residue;
post-fix, empty-`run_id` evidence can never be written again, so this is a
one-shot, not a recurring sweep. The home Ledger is outside the worker's repo
scope, so this is a PM action, keeping the worker's diff code-only.

## 7. Dogfood execution (the actual point)

PM = this Opus session. Sequence per the bundled contracts:
1. Freeze a contract/ticket scoped to `scripts/learning_miner.py` +
   `tests/test_learning_miner.py`.
2. Dispatch a **worker** subagent — TDD: write the §5 tests, watch RED, minimal
   GREEN.
3. Dispatch the **dual reviewers** (`auto-pilot-codex-reviewer` +
   `auto-pilot-claude-reviewer`), read-only, cross-verify findings.
4. Fix any findings → re-review until both APPROVE.
5. Dispatch **retro** — it emits a real `insights.jsonl` lesson for this run.

## 8. Verify / acceptance

- `python3 -m pytest tests/ -q` (incl. the 3 new tests) green.
- `python3 -m mypy scripts/ hooks/` + `ruff check scripts/ tests/ hooks/` clean.
- `python3 scripts/docs/check_doc_reference_integrity.py` OK (CONTEXT.md / ADR
  carry no `file:line` citations to break; verify anyway).
- `bash scripts/quality/check-module-size.sh` OK.
- Manual: a miner run with empty `run_id` writes 0 ticket files; with a real
  `run_id` still writes.

## 9. Dogfood success metric (honest)

This run proves the **agent layer mechanics** (PM → worker → dual review →
retro) end-to-end on a real fix, and that the fix itself holds. It does **not**
prove value-over-many-runs (that needs accumulation across real Runs and stays
deferred). Meta-property: if the Stop hook fires during this dogfood with an
empty `run_id`, the new guard means it will **not** pollute — the fix dogfoods
itself.

## 10. Non-goals

No fallback `run_id` (ADR 0001). No `_improvement.py` self-heal. No change to
the Stop hook gate. No promotion automation. No backfill. The fix is one line +
tests + a one-time delete; the loop exercise is the deliverable.
