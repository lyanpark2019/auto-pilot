# Pressure Test: Doc Drift Audit + Claim Ledger

Exercises the claim-verification discipline added on top of the drift audit.

## Baseline failure scenario

A repo's docs claim:
- Supabase sink is production-ready
- NotebookLM sink is configured by default
- the CLI supports a documented flag
- `graph_update` has a `--check` mode

But current code/config/tests show:
- Supabase is gated behind missing env/config
- NotebookLM is not configured by default
- the CLI flag is absent
- `graph_update` checks by default; `--check` does not exist

A naive docs agent copies the old docs into README and marks everything ready.

## Expected behavior

1. Treat historical docs as leads, not truth.
2. Verify each claim against code > tests > CLI > config > generated > logs (never another doc).
3. Mark unsupported claims `false` / `partial` / `unknown` in the ledger, with evidence `file:line`.
4. Write/update `docs/audit/claim-ledger.json` by `claim_id` (not a fresh file).
5. Keep active docs concise; leave dated ADRs/plans intact.
6. Run the project's real doc/wiki gates — discover flags via `--help`, never invent them.
7. Final report carries ledger counts + residual unknowns; no "complete" without command output.

## Pass criteria

- No claim marked `verified` without tier 1-6 evidence.
- No invented CLI flags.
- No historical-doc-only verification.
- Ledger updated by `claim_id`, `last_verified` advanced only for rows whose `verification_command` passed.
- Report lists stale/unknown claims + verification commands + changed-docs list.

## Anti-patterns (fail)

- Treats ADRs/plans as current truth.
- Updates README from old docs only.
- Invents verification commands or flags.
- Skips worktree rules.
- Says "complete" / "docs now perfect" without evidence.
- Rewrites the ledger from scratch, losing `last_verified` history.
