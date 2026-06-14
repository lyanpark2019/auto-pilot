---
type: spec
topic: two-tier deterministic→escalate loop (increment 3 of vault-substrate reframe)
source_commit: 9f83d2f
manual_edit: true
---

# Two-tier deterministic→escalate loop — increment 3

> Increment 3 of three. Sequence: closed-learning-loop (inc 1, DONE) →
> gated on-demand enrichment (inc 2, DONE) → **this**.
> Keystones locked in `docs/adr/0003-gated-ondemand-enrich-two-tier-escalation.md`;
> this spec decomposes them into phases.

## Problem

Today the deterministic loop either succeeds or hits a TERMINAL state and stops:

- **Doom-loop** (`scripts/orchestrator.py:239`): `cmd_pivot_check` sets
  `state["status"]="pivot-needed"` when the same finding repeats `count >= 3`. Terminal.
- **Broken review-evidence chain** (`scripts/_evidence.py:159,176`): `gate_phase_end`
  returns `("evidence_failed", message)` and the phase never advances. Terminal.
- **Promotion gate unmet** (`scripts/_promotion.py:142`): `transition` raises
  `PromotionError("promotion gate unmet: …")` when any `promotion_gate` field is not
  `True`. Terminal.

No typed escalation→tier-2-retry path exists for these cases today. inc 3 inserts
escalation **before** the terminal state so determinism-can't-solve cases get enriched
and retried exactly once.

## Decisions (locked — ADR 0003, quoted)

From `docs/adr/0003-gated-ondemand-enrich-two-tier-escalation.md`:

> **Tier-1 = deterministic (hooks, schemas, gates, fixed retry/state machines). When
> a tier-1 gate cannot resolve a case it emits a typed record —
> `{problem_class, tried, evidence, suggested_enrich_query}` — which the tier-2 agent
> loop consumes (and which may trigger an increment-2 enrichment, then retry). The
> boundary is explicit: a gate with a fixed rule stays tier-1; one without emits an
> escalation and hands to tier-2.**

> **Increments 2 and 3 share one seam: the escalation record is both the enrichment
> trigger and the tier-1→tier-2 boundary marker.**

The escalation record schema and producer (`scripts/_escalation.py`) shipped in inc 2
Phase 3. This spec wires them in at the three tier-1 give-up points and builds the
tier-2 resolver on top.

## Non-goals

- No loop rebuild — the existing PM→worker→review→verify chain is unchanged.
- No auto-relaxation of gate rules. A needed rule change is a harness change owned
  by the Hermes improvement-ticket path, NOT an escalation resolution.
- No continuous or background escalation scanning — on-demand only.
- No heavy infra (no vector DB, no consensus, no federation).
- No new `problem_class` enum values in Phase 1. The existing set in
  `scripts/_escalation.py:28–31` covers all three give-up points.

## Phase 1 — emit seam (deterministic, pure, testable)

Wire `_escalation.bump_or_create` at the three tier-1 give-up points. Each call is
additive — the existing terminal behavior is preserved; escalation is emitted in
addition to (not instead of) recording the terminal state.

**problem_class mapping (pinned):**

| Give-up point | File:line | problem_class |
|---|---|---|
| doom-loop `count >= 3` | `scripts/orchestrator.py:239` | `doom-loop` |
| promotion FSM `PromotionError` on unmet gate fields | `scripts/_promotion.py:142` | `promotion-gate-unmet` |
| review-evidence chain failure | `scripts/_evidence.py:176` | `contract-schema-gap` |

The remaining enum values (`unknown-library`, `unresolved-error`, `enrich-gate-reject`,
`other`) are emitted opportunistically by workers or the PM for other failure classes,
not new gates.

**scope:** `scripts/orchestrator.py` (emit at `cmd_pivot_check` doom-loop path),
`scripts/_promotion.py` (emit on `PromotionError` in `transition`),
`scripts/_evidence.py` (emit on `EvidenceError` in `gate_phase_end`),
`tests/test_escalation_emit.py` (new, fixture-driven).

**acceptance:**
- Each give-up point produces a record that validates against
  `schemas/escalation-record.schema.json` (`scripts/_escalation.py:55`).
- A fixture loop-state exercising each path emits a schema-valid record with the
  correct `problem_class` — deterministic, no network.
- Emitting does NOT change the exit code or state transition of the underlying give-up
  point; existing terminal behavior is byte-identical.
- Full CLAUDE.md verify list green (pytest + mypy + ruff + module-size gate).

## Phase 2 — tier-2 resolver + bounded retry (agent-driven)

A tier-2 step reads ONE open escalation record, drives enrichment via
`_escalation.drive_enrich` (`scripts/_escalation.py:238`), retries the failed tier-1
operation once with enriched knowledge available, then transitions the record per
the `TRANSITIONS` FSM (`scripts/_escalation.py:32`):

```
open → (drive_enrich) → enriched → (retry: gate passes) → resolved
                                 → (retry: gate still fails) → abandoned
```

Tier-2 resolver is a new agent (`agents/escalation-resolver.md`) dispatched by the PM
on an `open` escalation after a terminal tier-1 stop.

**Bounded:** exactly one `enrich + retry` cycle per escalation record. No
escalation-of-escalations. If the retry still fails the gate, state is `abandoned`.
Abandoned records are surfaced to the human via retro (`agents/retro.md:artifact
disposal` — retro reports them as unresolved gaps, does not fix them).

**What tier-2 MAY do:**
- Fetch external knowledge via `drive_enrich` → `fetch_and_persist`
  (`scripts/_escalation.py:238`) using `suggested_enrich_query` from the record.
- Retry the failed tier-1 gate once with enriched vault pages available.
- Inject enriched knowledge into the dispatch bundle for the retry.

**What tier-2 MAY NOT do:**
- Rewrite a gate rule (a gate-rule change is a Hermes improvement-ticket, not a
  resolution).
- Perform more than one enrich+retry per escalation.
- Emit a new escalation for the retry failure (the FSM `abandoned` terminal is the
  stop signal).

**scope:** `agents/escalation-resolver.md` (new), `scripts/_escalation.py` —
**NEW**: a `resolved`/`abandoned` writer (e.g. `record_resolution(record, new_state)`)
— locked RMW + `_can_transition` guard + `validate_escalation`, mirroring the shipped
`_record_enrichment` (`scripts/_escalation.py:209`). The `TRANSITIONS` *table* itself
is unchanged (no new state machine) — `tests/test_escalation_resolver.py` (new,
mocked fetcher).

**acceptance:**
- A worked escalation (fixture `open` record + `FakeFetcher` returning an admitted hit)
  drives `drive_enrich` → state `enriched`, then a mock-retry passes → `resolved`.
- A worked escalation where the mock-retry still fails → state `abandoned`.
- Both paths terminate in bounded steps (no loop); `TRANSITIONS` FSM rejects any
  attempt to re-open an `abandoned` or `resolved` record
  (`scripts/_escalation.py:40`).
- Abandoned records appear in the retro report (agent reads escalation ledger).

## Phase 3 — measure (deferred)

Signals: escalations emitted vs resolved vs abandoned; delta "determinism-stopped" →
"escalated-then-resolved". Instrument mirrors `scripts/measure_learnings_injection.py`
(deterministic scan over the escalation ledger, no network, CLI via
`orchestrator.py measure-escalation`). Deferred until Phase 1 + Phase 2 produce live
ledger data.

## Residuals and decisions resolved by this spec

- **tier-2 boundary definition (resolved):** fetch + retry + inject, bounded to 1 cycle,
  give-up → `abandoned` + human-surfaced via retro.
- **problem_class → emit-point mapping (resolved):** table above is canonical.
- **Retry mechanism (resolved):** the `TRANSITIONS` table
  (`scripts/_escalation.py:32–37`) is reused unchanged — no new state machine.
  However, Phase 2 MUST add a new resolution writer (`record_resolution`) to write
  the `resolved`/`abandoned` states; no such writer exists in the shipped module.
- **eTLD+1 / IDNA UTS-46 residuals (carried from inc 2):** remain open, zero-dep
  deferred; no change in this increment.
- **Phase 3 measurement (deferred):** explicitly deferred pending live ledger data.

## Disposal

Status: **ACTIVE** while inc 3 phases are open. Once inc 3 is shipped and measured,
retro (`agents/retro.md`) distills durable decisions into `docs/architecture.md` and
deletes this file, per the retro agent's artifact-disposal convention.
