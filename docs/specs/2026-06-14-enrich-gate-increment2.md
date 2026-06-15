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

**Phase-1 residuals — status as of Phase 2b.**

- *Blank-codepoint bypass* (U+3164/U+FFA0 Hangul fillers, U+2800 Braille blank,
  combining-mark-only Mn/Mc/Me): **CLOSED in Phase 2b** — `_has_visible_content` now
  NFKC-normalises a local copy and applies a `_BLANK_RENDER_CODEPOINTS` set +
  extended category block (Mn/Mc/Me added); the raw snippet passed to sha256/persist
  is never touched.
- *Punycode/IDN host equivalence* (`例え.テスト` vs `xn--r8jz45g.xn--zckzah`):
  **CLOSED in Phase 2b** — `_canonical_host` now IDNA-encodes via `.encode("idna")`
  so Unicode and xn-- forms map to the same string.
- *Multi-trailing-dot host collision* (`example.com..` not stripping to `example.com`):
  **CLOSED in Phase 2b** — `_canonical_host` now uses `.rstrip(".")` (full strip, not
  `[-1]`).
- *Registrable-domain / subdomain-collapse* (`www.reddit.com` vs `old.reddit.com`
  for the same thread): **OPEN (Path A — eTLD+1/IDNA host-canonicalization deferred,
  zero-dep posture retained)** — Python stdlib has no public-suffix list; a PSL-backed
  fix requires an external dep and is deferred until evidence-justified by a live
  producer. Mitigated agent-side: the fetch producer selects genuinely distinct domains.
- *IDNA2003 vs UTS-46 deviation characters* — stdlib `.encode("idna")` implements
  IDNA2003, which diverges from UTS-46/IDNA2008 for deviation chars (ß, ς, ZWJ); e.g.
  `straße.de` IDNA2003→`strasse.de` but UTS-46→`xn--strae-oqa.de`, so the two encodings
  of the same deviation-char domain can count as two independent hosts. **OPEN (Path A —
  same zero-dep / no live consumer deferral as eTLD+1 above)** — a correct fix needs
  the third-party `idna` (UTS-46) library.

## Phase 2 — enrichment fetch + persist — SPLIT

Phase 2 was split into two sub-phases:

### Phase 2a — gate-and-persist (deterministic) — DONE 2026-06-14

`scripts/_enrich_persist.py` + `orchestrator.py enrich` subcommand.
Takes candidate enrichment-evidence JSONs (file or directory), runs each through
the Phase-1 gate, persists ADMITted ones as vault `enrichment/enrich-<sha256>.md`
pages (UPSERT by sha, additive — never prune). No network calls; fully testable.
Tests: `tests/test_enrich_persist.py`.

### Phase 2b — live MCP fetch adapter — DONE 2026-06-14

On-demand fetch adapter (context7 → web → community via MCP), each hit shaped into an
enrichment-evidence candidate, run through the Phase-1 gate, and ADMITted candidates
persisted via `_enrich_persist.persist()`. Network-touching; the fetch layer is mockable
so tests stay deterministic. Also closes the Phase-1 host/codepoint residuals with a
real producer.

- scope: `scripts/_enrich_fetch.py` (Fetcher Protocol + shape_hit + fetch_and_persist),
  `agents/enrichment-fetcher.md` (live MCP I/O contract). acceptance: a mocked context7
  hit → gate → one byte-stable vault page; a community single-source hit → no page
  (gated out). 13 deterministic tests in `tests/test_enrich_fetch.py`, all green.

## Phase 3 — escalation-record schema + on-demand trigger (shared seam) — DONE 2026-06-14

The typed escalation record `{problem_class, tried, evidence, suggested_enrich_query}`
(schema + producer) — both the tier-1→tier-2 boundary marker (inc 3) and the enrich
trigger. A tier-1 gate that cannot resolve a case emits one; `suggested_enrich_query`
feeds Phase 2.

- scope: `schemas/escalation-record.schema.json` (9th schema), `scripts/_escalation.py`
  (fingerprint, bump_or_create RMW, drive_enrich seam, CLI escalation-record/list/enrich),
  `tests/test_escalation.py`, `agents/enrichment-fetcher.md` (Driven-by-escalation
  subsection), `CLAUDE.md` + `docs/architecture.md` (schema count 8→9 + helper-module row).
- acceptance: a worked escalation record validates and drives a Phase-2 enrich query;
  drive_enrich admits a FakeFetcher official hit → state=="enriched" + enrichment block
  stamped; all verify gates green.

## Phase 4a — gate-precision (DONE 2026-06-15)

`scripts/measure_enrich_precision.py` + `measure-enrich` CLI subcommand.
Deterministic admit/reject rate + per-tier breakdown + reason histogram +
evidence-complete rate + advisory-judge disagreement over candidate JSONs.
Tested on fixtures (mirrors the G1 `measure_learnings_injection.py` precedent —
instrument shipped, runs on real data later).
Acceptance met: fixture batches produce honest 0%/100%/mixed rates.

## Phase 4b — worker-output delta (DEFERRED)

Did enriched knowledge change worker output (honest delta)?  Needs a live
`enrichment-fetcher` MCP run + a worker A/B (pre/post vault enrichment pages);
non-deterministic, not unit-testable.  Now organically producible via
escalation-record → `drive_enrich`.  Defer to a dedicated experiment session.
