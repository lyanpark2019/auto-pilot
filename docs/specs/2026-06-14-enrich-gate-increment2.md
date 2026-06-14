---
type: spec
topic: gated on-demand enrichment (increment 2 of vault-substrate reframe)
source_commit: c3cd165
manual_edit: true
---

# Gated on-demand enrichment — increment 2

> Increment 2 of three. Sequence: closed-learning-loop (inc 1, DONE) → **this**
> → 2-tier deterministic→escalate (inc 3). Keystones locked in
> `docs/adr/0003-gated-ondemand-enrich-two-tier-escalation.md`; this spec
> decomposes them into phases. Identity SoT: `CONTEXT.md` (enrichment / escalation).

## Problem

The vault is read-only-grown today: injection (inc 1) pulls accumulated *internal*
learnings in, but nothing brings **verified external knowledge** (library docs, a
fixed-error writeup, a community gotcha) into the substrate. The operator's vision:
"continuous autoresearch enriches the vault with verified external knowledge." The
hard constraint (ADR 0003): **enrichment without a quality gate rots the vault into
low-signal junk** — so the gate is built first and is inseparable from any fetch.

## Decisions (locked — ADR 0003)

- **On-demand, targeted — not continuous background.** Enrich runs only on a detected
  knowledge gap (PM at plan time, or an inc-3 escalation), scoped to that gap.
- **Gate = deterministic-floor + evidence-persistence; LLM-judge advisory only.**
  Nothing enters the vault without persisted evidence: `snippet + URL + retrieved_date
  + SHA-256(snippet)`. Source tiers — official docs (context7) admit single-source;
  community (Reddit/forum/YouTube) require **≥2 independent corroboration OR a passing
  worktree repro**. An LLM-judge annotation is recorded but **never overrides** the
  deterministic verdict ("enforce with code, not prompts").
- **Source build order:** context7 → web → community (last); smallest-live-proof first.
- **Shared seam with inc 3:** the enrichment trigger is, in practice, the inc-3
  escalation record `{problem_class, tried, evidence, suggested_enrich_query}`.

## Non-goals (this increment)

- No continuous/background autoresearch workers (rejected, ADR 0003).
- No LLM-judge as the gate (advisory only).
- No 2-tier escalation control flow — that is increment 3 (this only defines the
  evidence/verdict the escalation will later feed).

## Phase 1 — the enrichment gate (deterministic core) — THIS PHASE

Build the gate before any fetch (it is the vault-rot prevention, inseparable per ADR
0003). Pure, no network, fully testable.

- scope: `schemas/enrichment-evidence.schema.json` (new), `scripts/_enrich_gate.py`
  (new, pure), `tests/test_enrich_gate.py` (new), `CLAUDE.md` + `docs/architecture.md`
  (schema count 7→8 + helper-module row).
- gate rule (deterministic):
  - **evidence-complete** = `snippet` non-empty AND `source_url` present AND
    `retrieved_date` valid ISO AND `sha256 == sha256(snippet.utf-8)` (recompute;
    mismatch = REJECT, tamper-evident, same discipline as the loop's evidence gate).
  - **official** tier → ADMIT iff evidence-complete.
  - **community** tier → ADMIT iff evidence-complete AND (`≥2 corroborations from
    hosts distinct from each other and from the primary host, each sha-valid` OR
    `repro_passed is True`); else REJECT.
  - `llm_judge` is recorded in the verdict output but never changes ADMIT/REJECT.
- acceptance: official complete→ADMIT; official missing/empty/SHA-mismatch→REJECT;
  community 1 corroboration→REJECT; community 2 independent corroborations→ADMIT;
  community repro_passed→ADMIT; community 2 corroborations same host→REJECT (not
  independent); advisory `llm_judge: reject` on an otherwise-ADMIT official does NOT
  flip the verdict. Full `CLAUDE.md` verify list green.

**Phase-1 residuals (documented, ADR-permitted; deferred to Phase 2 when a live
producer exists and the threat model is concrete).** The gate is not yet wired to any
fetcher, so each below needs an adversarial/sloppy *future* producer to arise — all
low-severity, none break sha-tamper detection or official-tier:

- *Host independence is a plain-hostname heuristic*, not a true source-independence
  proof. `www.reddit.com` vs `old.reddit.com` (same thread), a punycode `xn--` host vs
  its Unicode IDN form, and a pathological multi-trailing-dot `a.com..` (only one dot is
  stripped) each count as independent. (Single trailing-dot `a.com.` ≡ `a.com` IS
  handled + tested.)
- *Visually-blank but non-format codepoints* pass `_has_visible_content` (it rejects the
  whitespace + Cf/Cc/Zs/Zl/Zp classes): a snippet of only U+3164 Hangul filler / U+2800
  Braille-blank (categories Lo/So) or only combining marks (Mn) is admitted as a
  near-empty page.

Consolidated strategic fix (Phase 2): NFKC-normalise the snippet + a positive
"has a rendering codepoint" check (closes the blank-codepoint class), and a proper
IDNA / eTLD+1 host canonicaliser with full trailing-dot strip (closes the host class).

## Phase 2 — enrichment fetch + persist (later)

On-demand fetch adapter (context7 → web → community via MCP), each hit shaped into an
enrichment-evidence candidate, run through the Phase-1 gate, and ADMITted candidates
persisted as derived vault `enrichment/<sha>.md` pages (idempotent, one-way, like the
Phase-2 gotcha mirror). Network-touching; the fetch layer is mockable so tests stay
deterministic.

- scope: `scripts/_enrich_fetch.py` (MCP adapters), vault `enrichment/` page writer,
  orchestrator `enrich` subcommand. acceptance: a mocked context7 hit → gate → one
  byte-stable vault page; a community single-source hit → no page (gated out).

## Phase 3 — escalation-record schema + on-demand trigger (shared seam)

The typed escalation record `{problem_class, tried, evidence, suggested_enrich_query}`
(schema + producer) — both the tier-1→tier-2 boundary marker (inc 3) and the enrich
trigger. A tier-1 gate that cannot resolve a case emits one; `suggested_enrich_query`
feeds Phase 2.

- scope: `schemas/escalation-record.schema.json`, producer + emit seam. acceptance: a
  worked escalation record validates and drives a Phase-2 enrich query.

## Phase 4 — verify + measure (later)

Wire into suites; measure enrichment precision (admit/reject rate on real candidates)
and whether enriched knowledge changed worker output — honest delta, no make-believe.
