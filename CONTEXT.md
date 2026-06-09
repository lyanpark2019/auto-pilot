# auto-pilot — Hermes self-improvement loop

Glossary for the discover-only learning loop that mines recurring development
friction into a durable ledger. Terms here are the project's canonical language;
this file is a glossary, not a spec.

## Language

**Run**:
One execution of the auto-pilot loop, distinguished from every other execution
by a **run identity**.
_Avoid_: session, pass, iteration.

**Run identity** (`run_id`):
The non-empty identifier that makes one Run distinct from another. Absent run
identity, a Run cannot be counted toward accumulation.
_Avoid_: session id, uuid.

**Observation**:
One sighting of a friction pattern within a single Run, before it is given a
fingerprint identity.
_Avoid_: finding (a finding is a reviewer's output, a narrower thing), hit.

**Improvement ticket**:
The durable record of one recurring friction pattern, identified by its
fingerprint, carrying a state and accumulated evidence across Runs.
_Avoid_: issue, card, item.

**Ledger**:
The durable per-project store of improvement tickets, kept outside the target
repository so it never pollutes arbitrary repos.
_Avoid_: database, store, log.

**distinct_runs**:
The count of unique Runs that have observed a pattern. The promotion gate is
defined on this — deliberately cross-Run so a single Run cannot game promotion.
_Avoid_: occurrences (that counts sightings, not Runs), frequency.

**Verdict** (`promotable` | `thin`):
The miner's gate output for a scan — whether any ticket has reached its
promotion threshold. A property of a scan, never a state of a ticket.
_Avoid_: status, result.

**Non-persisting scan**:
A miner pass that computes and emits a Verdict without writing to the Ledger.
The required behaviour when a Run has no run identity (nothing to accumulate
against, so nothing is persisted).
_Avoid_: report-only, dry-run-mode (dry-run is the flag that requests it, not
the concept).

**Source**:
The origin classification of an Observation — one of `reviewer-finding`,
`doom-loop`, `pivot`, `insight`, `wasted-tool`. Sets the promotion threshold.
_Avoid_: kind, type, category.

**Candidate asset**:
The kind of artifact that would prevent a pattern's recurrence — one of
`skill`, `hook`, `schema`, `test`, `doc`, `cache`, or none. A classification,
never a path.
_Avoid_: fix, remediation, target.
