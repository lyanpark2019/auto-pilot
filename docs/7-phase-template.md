---
type: runbook
topic: auto-pilot-7-phase-fallback
source_commit: f726a9fa218eb29e2a01d54db4b94c0a1aaecb14
manual_edit: false
---

# 7-Phase fallback template

When auto-pilot is invoked on a repo whose spec has NO `## Phase N` headers, the `auto-pilot` skill tells the PM to fall back to this 7-phase template (workflow concept influenced by obra/superpowers' skill family; the 7-step sequence itself is auto-pilot's own synthesis), mapping the spec body into each phase's scope. This is a PM/skill instruction template, not a separate Python phase-expansion helper.

## Phases

### Phase 0 — Brainstorm

PM reads the spec, repo `CLAUDE.md`, recent commits, and open issues. Produces:
- `docs/auto-pilot/0-brainstorm.md` — open questions, hidden assumptions, alternatives considered
- Output is NOT code. Output is a structured intent doc.

Verify gate: tech-critic-lead approves the intent doc.

### Phase 1 — Spec

PM converts brainstorm output into a concrete spec with measurable acceptance criteria. Produces:
- `docs/specs/<date>-<slug>.md` (the canonical spec auto-pilot will then drive against in re-runs)
- Phase headers added so future runs use the spec directly, not this fallback

Verify gate: spec contains acceptance criteria for every claim. No "TBD" sections.

### Phase 2 — Plan

PM decomposes the spec into non-overlapping work contracts. Produces:
- `.planning/auto-pilot/plan.json` — contracts with `scope_files`, `acceptance`, `est_loc`
- Each contract is sized to one MVP-ticket per Superpowers atomic-task rule

Verify gate: tech-critic-lead approves each contract (`features = cost`).

### Phase 3 — TDD

For each contract, dispatch a worker whose ONLY job is to write the failing tests. Produces:
- Failing test files only — no implementation
- Worker explicitly verifies `pnpm test` / `pytest` fails for the new tests

Verify gate: `review-gatekeeper` in `tdd-gate` mode confirms tests exist for every contract behavior + test suite is RED at the new tests.

### Phase 4 — Subagent Dev (Build)

For each contract, dispatch a worker (Sonnet 4.6 1M ctx) to make the failing tests pass. Produces:
- Minimal implementation per contract
- `pnpm test` / `pytest` green

Verify gate: full review fan-out (auto-pilot-codex-reviewer + auto-pilot-claude-reviewer + review-gatekeeper + matching specialists). All APPROVE.

### Phase 5 — Review

Aggregate review pass over the merged Phase-4 work. PM dispatches a single cold auto-pilot-claude-reviewer over the cumulative diff (not per-contract). Catches cross-contract issues missed in per-worker review. Produces:
- `docs/auto-pilot/5-review.md` — findings + dispositions

Verify gate: zero open P0/P1 findings. P2 findings logged but not blocking.

### Phase 6 — Finalize

PM runs the project's full verify checklist one last time on the merged branch. Produces:
- `docs/auto-pilot/6-final-report.md` — coverage, perf delta, doc updates, residual risks
- `CHANGELOG.md` entry if the project has one

Verify gate: all of `pnpm test && pnpm lint && pnpm typecheck && pnpm build` green. PM updates state.json `status=success`.

## How PM detects which template applies

The PM-level rule lives in `skills/auto-pilot/SKILL.md`: if the spec has `## Phase N` headers, use those phases; otherwise use this template. The deterministic helper currently does less: `scripts/orchestrator.py` counts `#`/`##`/`### Phase` headings outside fenced code and floors at 1 via `_count_phases()`. Therefore this document must not imply a separate Python `detect_phase_mode()` implementation exists.

In `7-phase-fallback`, PM treats this template as the phase recipe; in `spec-defined`, PM uses the spec's own phase headers and ignores this template.

## Mapping to existing skills

Each phase loops the same auto-pilot core (plan contracts → tech-critic gate → worker fan-out → review fan-out → verify → commit), but with different scope per phase:

| Phase | Worker outputs |
|---|---|
| 0 Brainstorm | docs only |
| 1 Spec | docs only |
| 2 Plan | docs + plan.json |
| 3 TDD | test files only |
| 4 Build | implementation files |
| 5 Review | docs only |
| 6 Finalize | report + CHANGELOG |

## Why this template (not just "let PM improvise")

Without a spec, an autonomous loop will hallucinate scope. The 7-phase template forces brainstorm→spec→plan to happen as code-free deliverables before any worker touches the codebase. This is the single biggest defense against the auto-pilot building the wrong thing fast.
