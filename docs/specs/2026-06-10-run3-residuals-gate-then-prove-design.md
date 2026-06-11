---
type: spec
topic: run3-residuals-gate-then-prove
manual_edit: true
---

# Run-3 Residuals — Gate-then-prove Design

**Date**: 2026-06-10
**Status**: approved design (brainstorm session) — input to implementation plan
**Closes**: ① contract-layer bypass (run-3 finding) ② headless dispatch guard (P2)
③ REJECT-round live proof ④ merge-conflict live proof

## Problem evidence (run 3, spec `2026-06-10-run3-multiphase-smoke.md`)

Phase 1 used the full contract layer (both reviewer JSON tickets + schema-valid
`outputs/*/review.json`). Phase 2 did NOT: `tickets/codex-reviewer.json` never
created, `outputs/claude-reviewer/` empty, no codex output dir — yet `state.json`
recorded `verdict: APPROVE`, phase merged. Same prompts, different phase →
non-determinism. Two structural holes:

1. `scripts/_dispatch.py:384` — `_expected_agents` derives the expected set from
   dirs that exist; an undispatched reviewer is never expected, never validated.
2. `scripts/orchestrator.py:169` — `cmd_phase_end` accepts `--status success`
   with zero evidence validation. (`_expected_agents` at `_dispatch.py:384`
   feeds only the wait loop — not an evidence check — so it is left as-is.)
3. `hooks/dispatch-contract-gate.sh` — documented "marker absent → allow" bypass
   lets ticket-less dispatch through.

Principle violated: **evidence over trust** / **enforce with code, not prompts**.

## §1 Exit evidence gate (load-bearing)

- New `assert_round_evidence(contract_dir)` in `scripts/_dispatch.py`. Evidence
  chain (no schema change — `review.schema.json` carries no diff sha; binding
  goes through the reviewer ticket):
  1. `review-input/frozen.diff` exists; recomputed SHA-256 ==
     `review-input/frozen.diff.sha256` content.
  2. both `tickets/{codex-reviewer,claude-reviewer}.json` exist with
     `diff_sha256` equal to that value.
  3. both `outputs/{codex-reviewer,claude-reviewer}/review.json` exist,
     schema-valid, `contract_id` == the round's contract id, verdict present.
- `_expected_agents` (`_dispatch.py:384`) is deliberately NOT changed: forcing
  both reviewers as always-expected would hang `collect_round_outcome` on
  worker-only collections. Presence-of-both is enforced at the exit gate below,
  not in the wait loop.
- `cmd_phase_end --status success`: walk the current phase's contract round
  dirs; final round must pass `assert_round_evidence` AND both verdicts APPROVE.
  Fail → exit 2, `BLOCKED` on stderr, state untouched (no partial write).
  `--status failed|stopped` exempt.

## §2 Entry gate fail-closed (reviewer-scoped)

Workers dispatch as `subagent_type: general-purpose` (pm-orchestrator.md:99) —
indistinguishable from legit non-worker dispatch by type, so they CANNOT be
gated on type. Reviewers always carry a fixed type and are always ticketed.
So `hooks/dispatch-contract-gate.sh` marker-absent branch (current `exit 0` at
line 68): deny when `tool_input.subagent_type` contains
`auto-pilot-codex-reviewer` or `auto-pilot-claude-reviewer` AND no `TICKET=`
path / `contract_dir=` marker in the prompt AND an active run exists in the cwd
repo (`.planning/auto-pilot/state.json` status == `running`). Deny reason:
prepare via `prepare_subagent_ticket`, dispatch with `TICKET=<path>`. No active
run / non-reviewer type / unparseable stdin → allow (preserves foreign-repo
false-deny history + fail-open convention).

This catches "reviewer dispatched ad-hoc, bypassing the ticket/diff-sha
binding". It does NOT catch "reviewer never dispatched at all" — that is the
§1 exit gate's job (defense-in-depth, the two are complementary).

## §3 Headless background-dispatch guard

`scripts/headless-loop.py:200` already injects `HARNESS_HEADLESS=1` into the
spawned session env — hooks inherit it, so pid-to-session attribution is
unnecessary. New `hooks/headless-sync-dispatch-guard.sh` (PreToolUse, matcher
Task|Bash): env set + `tool_input.run_in_background == true` → deny. Wire into
`hooks/hooks.json`, `chmod +x`. Residual: Bash trailing-`&` backgrounding not
covered (fuzzy detection, deferred deliberately).

## §4 Doc-drift rider

Agent contracts / SKILL.md hard-code "Opus 4.7 main session" → reword
model-agnostic: "main session PM (currently Fable 5)". Worker "Sonnet 4.6 (1M
context)" stays — still accurate.

## §5 Run-4 dogfood spec (separate live-run input doc, one headless run)

- **Phase 1 — REJECT round (1 contract)**: seeded defect — worker round-1 ticket
  instructs committing WITHOUT the trailer block while spec acceptance requires
  it. Objective + checklist-visible → reviewers REJECT → round-2 fix → APPROVE →
  merge. If reviewers miss it: recorded as reviewer-quality P1 finding (both
  outcomes are signal).
- **Phase 2 — merge-conflict + multi-contract parallel (2 contracts)**: both
  append a test at EOF of the SAME test file → guaranteed textual conflict.
  A merges; B's `apply_to_main` returns conflict (`git am --abort`, main stays
  clean) → PM re-dispatches B rebased on new main → merge. Acceptance: conflict
  event logged, main never dirty, both commits land.
- Run headless (`/auto-pilot-server`) → proves §3 guard + F-6 sync prompts live;
  two phases in-loop re-proves multi-phase under the new gates.

## Error handling

Guards exit 2 + `BLOCKED` stderr; hooks deny via `permissionDecision` JSON;
phase-end failure writes nothing; live-run hard failure stops and reports — no
silent fallback.

## Testing

- pytest: evidence-gate matrix (missing review.json / invalid schema / sha
  mismatch / non-APPROVE verdict / pass), `cmd_phase_end` refusal paths,
  `_expected_agents` fix.
- Hook self-tests (script-style, matching `hooks/test_guard_destructive.py`
  pattern): §2 deny/allow matrix, §3 deny/allow matrix.
- Full gates: pytest + mypy + ruff + shellcheck + module-size + doc-ref.

## Residual risks (stated)

- Seeded defect is not a 100%-deterministic REJECT; a miss is itself a P1
  reviewer finding.
- Entry gate keys on `subagent_type` — a generic-agent dispatch slips it; exit
  gate still blocks evidence-free advance (defense-in-depth rationale).
- Bash `&` backgrounding uncovered by §3.
- `review.json` itself carries no diff sha — binding relies on the reviewer
  ticket + frozen.diff recompute; a reviewer reviewing the wrong diff but
  emitting matching `contract_id` is not detectable from artifacts alone.

## Non-goals

No reviewer-agent contract changes, no new schemas, no swarm/vault surface
changes, no Step-3 digest work.

## Disposal

Shipped → distill into `docs/architecture.md` (gates section) then delete;
run-4 spec doc follows live-run-input retention rules.
