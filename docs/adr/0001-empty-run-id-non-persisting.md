# Empty run identity ⇒ non-persisting scan; never synthesize a fallback run_id

Status: accepted (2026-06-09)

When the learning miner runs without a **run identity** (empty `run_id` — e.g. a
standalone retro over git history, a stale/stub `state.json`, or any invocation
outside an orchestrator-initialised Run), it performs a **non-persisting scan**:
it computes and emits a Verdict but writes nothing to the Ledger. We deliberately
do **not** synthesize a fallback run identity (date, git HEAD, etc.) to let such
scans accumulate.

## Considered options

- **Synthesize a fallback `run_id`** (date- or HEAD-derived) so standalone scans
  accumulate `distinct_runs`. **Rejected.** A date fallback lets the same
  unchanged history re-mine on three different days and falsely cross the
  promotion gate — exactly the single-source gaming `distinct_runs` exists to
  prevent. A HEAD fallback re-counts re-emitted old lessons whenever the repo
  advances for any reason. Either re-imports gaming the dual-review already
  killed.
- **Persist with the empty `run_id` as-is.** Rejected — produces permanently
  un-promotable tickets (`distinct_runs` stuck at 1) that are pure Ledger
  clutter (this is the defect this decision fixes).

## Consequences

- Accumulation toward promotion requires genuine, distinct Runs — only real
  auto-pilot loop executions (which mint a real run identity) move
  `distinct_runs`. This is intended, not a limitation to be "fixed".
- A future contributor who adds a fallback `run_id` to "make standalone retros
  count" is reintroducing the gaming vector. Don't. The gate's integrity depends
  on run identity being real.
