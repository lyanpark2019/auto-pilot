# Design — structured insights as a miner input (class-keyed)

> Status: approved (autonomous, 2026-06-09). Follows the Hermes-loop MVP
> ([design](2026-06-09-hermes-loop-mvp-design.md)) and the live-wiring spec
> ([wire-live](2026-06-09-hermes-wire-live-design.md)). This is the MVP design's
> own flagged **future spec**: §residual said "a structured `insights.jsonl`
> from retro is a separate future spec that *does* touch `retro`." Not a
> re-litigation of the dropped *prose-parsing* — this is the structured path.

## 1. Problem (measured, not assumed)

The MVP miner accumulates only on a **literal** fingerprint (source ‖ file
basename ‖ normalized-issue ‖ asset). Two measurements show this misses the
high-value signal:

- **Proxy eval** (`learning_miner` run on insights.md-shaped findings): the same
  root cause reworded across rounds produces N *separate* thin tickets; a class
  recurring across files splits on `file_basename`; within-run thrash never
  raises `distinct_runs`.
- **Real corpus** (~230 commits over 11 session-days): recurring *classes* exist
  but are **weaker and more heterogeneous than first stated** (see correction
  below). The defensible point stands — the same class surfaces with **different
  wording every time** (e.g. commit subjects "fail-open observability" vs "was
  fail-open"), so a literal fingerprint fragments it and it never reaches the
  `distinct_runs` gate.

> **Correction (2026-06-09, dual-review of the next-step decision).** This
> section originally claimed "293 commits", and "`format-drift` and `fixture`
> each span **8** distinct session-days; `silent` 6; `race` 5; `marker` 4".
> Those numbers do **not** reproduce and overstated the signal:
> - Corpus is **230** commits, not 293.
> - `format-drift` is a **grep artifact / grab-bag**: `git log --pretty=%s | grep
>   -ic format` = **0**; the figure came from bare `drift` (8 commits) spanning
>   six *unrelated* kinds — graphify drift, asset-count drift, prompt-schema
>   drift, doc-count drift, spec-drift review-lens, doc-drift-audit tooling,
>   anchor-guard, composition-root harness-drift. It is **not one fixable
>   class**, and its asset-count sub-class is already CI-guarded
>   (`scripts/docs/check_doc_reference_integrity.py`, wired at `.github/workflows/ci.yml:40`).
> - By distinct commit-day on subjects: `format-drift`(bare-drift) 6, `fixture`
>   3, `shellcheck` 3, `silent` 2, `fail-open` 2, rest ≤1 — only one class
>   nominally clears the `insight: 3` gate, and that one is heterogeneous.
> The class-key **mechanism** in §2 remains sound (semantic recurrence is real),
> but this corpus does **not** establish "real and strong" per-class volume. The
> honest state: signal weak + method-dependent; let live runs accumulate honest
> `distinct_runs` before building any promotion machinery on top.

Conclusion: the recurring signal is **semantic / class-level**, and a
deterministic literal fingerprint cannot cluster it. The human already clusters
at class level in `.claude/insights.md`. So the fix is to let `retro` emit that
human/agent clustering as a **structured, class-keyed** input the miner reads.

## 2. Decision — `retro` emits `insights.jsonl`; miner adds `scan_insights`

`scan_insights` is the missing scanner for a source the miner already
anticipates: `PROMOTION_THRESHOLDS` in `scripts/learning_miner.py` already
carries `"insight": 3`. Only the scanner is absent.

**Why class-keyed (the measurement's lesson):** for `source="insight"` the
fingerprint must key on a **stable class tag**, NOT free wording and NOT a file:
- `Observation.issue` = the canonical class tag (e.g. `fail-open`).
- `Observation.file_basename` = `""` (a class is cross-file — keying on a file
  would re-fragment exactly what we are de-fragmenting).
- `Observation.snippet` = the full JSON line (human one-liner kept as evidence).

So `compute_fingerprint("insight", "", normalize_issue(class_tag), asset)` is
stable across sessions → `distinct_runs` accumulates on the class → promotes at
`insight: 3` distinct runs.

## 3. Input — `.planning/auto-pilot/insights.jsonl`

One JSON object per line, written by `retro` alongside its prose
`.claude/insights.md` append:

```json
{"class": "fail-open", "issue": "guard fails open on compound command", "candidate_asset": "hook"}
```

- `class` — REQUIRED, the canonical class tag, drives the fingerprint. Recommended
  vocabulary (the measured recurring classes): `format-drift`, `fixture-shape`,
  `shellcheck`, `marker-precision`, `silent-failure`, `race`, `fail-open`,
  `reentry`, `ordering`, `dead-path-doc`. Free tags allowed; `normalize_issue`
  lowercases + collapses whitespace so minor variants merge.
- `issue` — human one-liner (evidence/snippet; does NOT drive identity).
- `candidate_asset` — enum `skill|hook|schema|test|doc|cache` or null (out-of-enum
  coerced to null, same as `scan_reviewer_findings`).

Same `.planning/auto-pilot/` location as `critic-rejections-*.jsonl` (per-run
scratch the miner reads each run). Missing-key / malformed lines are tolerated
(degrade, never crash) exactly like the reviewer scanner.

## 4. `scan_insights(repo_root, run_id) -> list[Observation]`

Reads `.planning/auto-pilot/insights.jsonl`. Per non-empty line:
- parse JSON; skip non-dict / unparseable.
- `class_tag = finding["class"]` if a non-empty str, else `finding["issue"]`
  (degrade), else skip the line (no key → no stable identity).
- coerce `candidate_asset` to the enum or null (`VALID_ASSET_TYPES`).
- `Observation(source="insight", file_basename="", issue=class_tag,
  candidate_asset=..., run_id=run_id, snippet=json.dumps(finding)[:500])`.

Wire into `run_miner` after `scan_reviewer_findings` + `scan_doom_loops`.

## 5. `retro` contract change (`agents/retro.md`)

Add a step: when distilling a recurring lesson, in addition to the prose
`.claude/insights.md` append, append a structured line to
`.planning/auto-pilot/insights.jsonl` with `{class, issue, candidate_asset}`,
picking `class` from the recommended vocabulary. retro stays read-only w.r.t.
source code; it only writes its own ledger + this sidecar. No verdicts, never
blocks (unchanged retro contract).

## 6. Testing (TDD)

`tests/test_learning_miner.py`:
- `scan_insights` parses a well-formed line → one `Observation(source="insight",
  file_basename="", issue=<class>)`.
- **cross-run promotion**: same class in 3 distinct runs → `distinct_runs=3` →
  verdict `promotable` (insight threshold).
- 2 distinct runs → still `thin` (below insight threshold of 3) — distinguishes
  insight (3) from reviewer (2).
- **class-key, not file/wording**: two lines, same `class`, different `issue`
  wording → ONE ticket (proves de-fragmentation — the whole point).
- malformed line / missing `class` (fallback to `issue`) / out-of-enum asset →
  tolerated, coerced.

## 7. Doc sync

- `docs/architecture.md` and `CLAUDE.md` if any asset/count claim changes (no new
  hook/agent file is added — `scan_insights` is a function, `retro.md` is edited
  in place — so counts likely unchanged; verify with doc-integrity).

## 8. Non-goals

No prose parsing of the existing `.claude/insights.md` (the MVP-rejected path —
existing prose lessons stay human-only; this is forward-looking structured
emission). No backfill of historical insights. No change to the reviewer /
doom-loop scanners. No promotion automation (still discover-only). No FSM/decay.

## 9. Residual risk

- **retro emission reliability**: `retro` is an LLM agent; a missing or sloppy
  `class` degrades (fallback to `issue`, or line skipped) — never crashes, but a
  mis-tagged class fragments like before. Mitigated by the recommended vocabulary
  + `normalize_issue`; not eliminated. The structured sidecar is best-effort.
- **Payoff is forward-looking**: value accrues only as future runs accumulate
  class-keyed insights across `distinct_runs ≥ 3`. No immediate effect on the
  empty ledger.
- **Effect still unmeasured**: "does a promoted insight, once actioned, reduce
  future findings" remains the ultimate KPI, requiring live-run data + the
  (still-deferred) assisted-promotion + eval loop.
