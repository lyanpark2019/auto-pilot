---
type: spec
topic: closed-learning-loop (increment 1 of vault-substrate reframe)
source_commit: d1d2eb2
manual_edit: true
---

# Closed learning loop — increment 1

> Increment 1 of three (grilled 2026-06-14). Sequence: **this** → enrich+gate
> (autoresearch external knowledge) → 2-tier deterministic→escalate control flow.
> Increments 2/3 are designed only after this lands live and produces data
> ("measure before optimizing"). Identity SoT: `CONTEXT.md`. Decision: `docs/adr/0002-ledger-sot-vault-mirror.md`.

> **REMOVED 2026-06-20.** This increment shipped, then its class-nudge injection
> was deleted as a measured no-op (see auto-memory learning-loop-archon-port and
> the removal note in `docs/architecture.md`). This page is retained as the
> historical design record; the mechanism it describes is no longer in the code.

## Problem

The learning loop is **open**. Mistakes are captured (improvement-ticket miner: critic
rejections, pivots, insights; retro: gotchas) but never read back: the dispatch
`context-bundle` carries only `spec.md`, the `CLAUDE.md` chain, and the graphify
`project-context.md`. A problem the operator already hit 2+ times is re-derived
from scratch every run. The operator's stated pain: "store every mistake so the
same problem is prevented or fast-solved next time," and "the installed project's
conversation history lands in Obsidian."

## Decisions (locked 2026-06-14)

- **Store split** — Ledger (JSON, outside repo) = machine SoT + injection source;
  vault = one-way human mirror of `promotable`+ tickets only. ADR 0002.
- **Inject only gate-passed learnings** — the existing `distinct_runs` gate is the
  noise filter. One-off observations are never injected. Serves "same problem"
  directly: a `promotable` ticket means ≥2 distinct Runs hit it.
- **Relevance = deterministic scope match** — a ticket is relevant to a contract
  when the contract's `scope_files` intersect the ticket's evidence files/assets.
  Semantic (graphify) match is **deferred to G1** — add only if recall proves
  insufficient on real external-repo data.
- **Conversation capture = Stop-hook auto + distill** — at session end a Stop hook
  distills the session (decisions / mistakes / what worked / what didn't) into a
  vault session-record page (this is what gets indexed and fed to the miner); the
  raw transcript is linked, not inlined. "Store everything" = raw is archived;
  vault stays clean = only the distillate is indexed.
- **Reuse, don't rebuild** — capture is the existing improvement-ticket miner + retro plus the
  new distill hook; injection is one new resolver + a `snapshot_context` extension.

## Non-goals (this increment)

- No external autoresearch (context7 / web / YouTube / Reddit) — that is increment 2,
  and it MUST ship with its quality/relevance gate.
- No semantic relevance match — deferred to G1.
- No 2-tier deterministic→escalate control flow — increment 3.
- No raw-transcript injection — only the distillate and gate-passed Ledger tickets.

## Phase 1 — session distill capture

A `Stop` hook distills the just-ended session into a vault session-record page and
links the raw transcript. Advisory (never blocks; always exit 0), reentry-guarded,
once per session (same dedup discipline as `learning-miner-stop`).

- scope: `hooks/` (new `session-distill-stop.sh` + self-test), `hooks/hooks.json`,
  vault export seam for a `sessions/` page type.
- acceptance: a session produces one vault session-record page (front-matter:
  project, run_id, date, raw-transcript link); raw transcript path resolves; hook
  exits 0 even on malformed input; self-test passes.

## Phase 2 — promotable → vault mirror

A derived, idempotent mirror writes each `promotable`+ Ledger ticket as a vault
gotcha page. Re-running overwrites (never appends duplicates). Mirror is never
hand-authored.

- scope: `scripts/_improvement.py` or a new `scripts/_mirror_learnings.py`,
  `orchestrator.py` subcommand, vault gotcha page template.
- acceptance: N `promotable` tickets → N vault gotcha pages, re-run is byte-stable;
  un-promotable tickets produce no page; each page links back to its ticket fingerprint.

## Phase 3 — injection resolver (the loop-closing seam)

A resolver reads the Ledger, selects tickets where `state ∈ {promotable, promoted}`
AND `scope_files ∩ ticket.evidence_files ≠ ∅`, renders `context-bundle/learnings.md`,
and `snapshot_context` SHA-pins it into `snapshot_shas.learnings` + MANIFEST.
`verify_snapshots` fail-closes on declared-but-missing/tampered bytes (same contract
as `project_context`). Absent/empty selection → no file, "ran learnings-blind" log,
never blocks dispatch.

- scope: new `scripts/_learnings.py` (resolver, pure), `scripts/_contract.py`
  (`snapshot_context` + `verify_snapshots` extension), `schemas/contract.schema.json`
  (`snapshot_shas.learnings` OPTIONAL), `agents/pm-orchestrator.md` dispatch step,
  the dispatch prompt template (list `learnings.md`).
- acceptance: a contract whose `scope_files` hit a `promotable` ticket gets a
  SHA-pinned `learnings.md` in its bundle; tamper → `verify_snapshots` rejects;
  no-match contract dispatches learnings-blind with the log line; schema stays
  `additionalProperties:false`.

## Phase 4 — verify + measure

Wire the increment into the existing suites and measure whether injection helps —
no make-believe; report the honest delta.

- scope: `tests/` (resolver unit, snapshot tamper, hook self-test), eval oracle if cheap.
- acceptance: full `CLAUDE.md` verify list green (pytest + mypy + ruff + hook
  self-tests + bats + module-size + doc-reference-integrity); a recorded before/after
  on at least one dogfood run noting whether injected learnings changed worker output.
  Relevance recall (did scope-match miss a relevant ticket?) recorded as the G1 input
  for the deferred semantic-match decision.
