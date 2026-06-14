# Knowledge enrichment is gated + on-demand; the loop is two-tier with typed escalation records

Status: accepted (2026-06-14) — increments 2 & 3 of the vault-substrate reframe; built after increment 1 lands.

Grilled 2026-06-14. Two coupled control-flow decisions for the vault-grounded loop.

## Increment 2 — autoresearch enrichment

- **On-demand, targeted — not continuous background.** Enrichment runs only on a
  detected knowledge gap (PM identifies a needed library/error at plan time, or an
  escalation surfaces one), and researches just that, scoped. Rejected: ruflo-style
  always-on background workers — expensive, noisy, no evidence of need ("measure
  before optimizing"). The enrichment trigger is, in practice, the increment-3
  escalation signal (the two are coupled).
- **Gate is deterministic-floor + evidence-persistence; LLM-judge is advisory only.**
  Nothing enters the vault without persisted evidence (snippet + URL + retrieved-date +
  SHA). Source tiers: official docs (context7) admit single-source; community
  (Reddit/forum/YouTube) require ≥2 independent corroboration OR a passing worktree
  repro. Rejected: an LLM-judge as the gate (non-deterministic, can hallucinate-approve
  — violates "enforce with code, not prompts"). The gate is **inseparable** from
  enrichment: without it the vault rots into low-signal junk.
- **Source build order:** context7 → web → community (last), following the gate tiers
  and the smallest-live-proof discipline.

## Increment 3 — two-tier deterministic → escalate

- **Explicit, typed escalation records — not ad-hoc PM judgment.** Tier-1 is the
  deterministic layer (hooks, schemas, gates, fixed retry/state machines). When a
  tier-1 gate cannot resolve a case it emits a typed record —
  `{problem_class, tried, evidence, suggested_enrich_query}` — which the tier-2 agent
  loop consumes (and which may trigger an increment-2 enrichment, then retry). The
  boundary is explicit: **a gate with a fixed rule stays tier-1; one without emits an
  escalation and hands to tier-2.** This is the code form of "solve deterministically
  first; the second loop handles only what determinism could not."
- Rejected: keep PM ad-hoc escalation (no code boundary — non-deterministic,
  inconsistent, untestable). Rejected: tier-2-first / adaptation-first (ruflo GOAP
  style — expensive, inverts the "deterministic first" principle).

## Consequences

- Increments 2 and 3 share one seam: the escalation record is both the enrichment
  trigger and the tier-1→tier-2 boundary marker.
- These designs are recorded but **not yet phase-specced** — full specs are written
  after increment 1 (`docs/specs/2026-06-14-closed-learning-loop.md`) lands live and
  produces data, per the project's measure-first discipline.
