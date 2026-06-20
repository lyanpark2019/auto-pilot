# Mistakes live in the structured ledger (SoT); the Obsidian vault mirrors only promotable ones

Status: accepted (2026-06-14) — **superseded 2026-06-20** (the learning loop this
ADR governed was removed as a measured no-op; retained as a historical record).

> **Naming note (2026-06-15):** the internal codename "Hermes loop" / "Hermes ledger" was
> renamed to "improvement-ticket loop" / "improvement-ticket ledger" to avoid collision with
> Nous Research's Hermes Agent (an OSS agent whose flagship feature is also a "closed learning
> loop"). Code identifiers (`learning_miner`, `_improvement`, `_promotion`, etc.) are unchanged.

The closed learning loop needs a store that injection can read deterministically —
only **gate-passed** learnings, machine-readable, fast. The existing improvement-ticket
**Ledger** (JSON, outside the target repo) already is that: fingerprinted tickets
with `distinct_runs` gate counters. So the Ledger stays the **single source of
truth** for injection. The Obsidian **vault** receives a one-way **mirror** of
only `promotable`+ tickets as human-browsable gotcha pages — giving the operator
"everything visible in Obsidian" without making the gate parse prose.

## Considered options

- **Make the vault the single store** — write improvement-ticket ledger entries as Obsidian pages with
  gate counters in frontmatter. **Rejected.** The promotion gate would then parse
  markdown frontmatter on every scan — fragile, and it pollutes a human-curated vault
  with raw one-off observations (most never reach `promotable`). The vision "everything
  in Obsidian" is satisfied by the mirror, not by forcing the machine store into prose.
- **Ledger only; vault not involved in mistakes** — Rejected. Contradicts the
  vault-as-substrate identity (`CONTEXT.md`) and the operator's "all my problems live in
  Obsidian" requirement; loses the human-browsable view.

## Consequences

- Two stores with a clear contract: Ledger = machine SoT + injection source; vault =
  human mirror of promotable learnings only. The mirror is **derived**, never authored
  directly — re-deriving it must be idempotent.
- Injection (`context-bundle/learnings.md`) reads the Ledger, never the vault prose.
- One-off observations (un-promotable) stay out of the vault by design; finding them
  requires the Ledger, not the vault. Intended, not a gap.
- See `docs/specs/2026-06-14-closed-learning-loop.md` for the increment that builds this.
