---
type: spec
topic: model-routing-enforcement
manual_edit: true
---

# Model-Routing Enforcement + Codex/Verifier Efficiency (A+B) — Design

**Date**: 2026-06-12
**Status**: approved design (brainstorm) — input to implementation plan
**Scope**: Slice A (routing enforcement) + Slice B (codex/verifier efficiency).
Slice C (history ledger + PM rebalance) is DEFERRED to its own spec — it consumes
this slice's telemetry, so it cannot precede it.

## Problem evidence

The routing convention is fully authored as prose in
`skills/auto-pilot/references/model-routing.md` (tier ladder, role×model matrix,
codex dispatch, verifier convention, ledger rules) and cited by global
`~/.claude/CLAUDE.md`. But it is **prose, not enforced or wired**:

1. `agents/auto-pilot-codex-reviewer.md:39` — `codex exec` pins **no**
   `model_reasoning_effort`, so codex runs at its default (high) on every diff
   regardless of risk. This is the root cause of "codex가 자주 멈추거나 너무 오래".
2. No wall-clock bound on the live-loop codex call → an unbounded hang
   (`_reviewer_wrapper.py` has a 300/480s watchdog, but only on the headless
   SUBPROCESS path — the interactive PM dispatches reviewers via the Agent tool,
   which that watchdog never sees).
3. No reviewer progress signal — workers write `outputs/worker/status.json`;
   reviewers write nothing, so the PM is blind until `done.marker`.
4. "Verifier ≥ PM tier" (model-routing.md:38) is unenforced — a verifier could
   be dispatched under-tier with no guard.

Principle: **enforce with code, not prompts.**

## §1 Machine-readable matrix (the SoT seam)

- New `skills/auto-pilot/references/model-routing.yaml` — machine form of the
  `.md` matrix: `tier_ladder`, `roles` (role→default model),
  `codex_effort_by_risk_tier` (`none→low · low→low · medium→medium · high→high ·
  critical→xhigh`), and `codex_timeout_s` / `codex_retry_s` (§3 budgets). The
  `.md` stays the human SoT and cites the `.yaml`
  (`file:line`); the `.yaml` is what code reads. (Two-tree rule: one is source,
  one is citation — no duplicated fact.)
- New `scripts/_routing.py` — narrow resolver: `effort_for_tier(tier: str) -> str`
  and `verifier_min_tier() -> str`, both reading the `.yaml`. NO general
  role×task resolver in v1 (YAGNI — slice C's rebalance needs structured records,
  not a dispatch resolver).

## §2 Codex speed by default (root cause)

`agents/auto-pilot-codex-reviewer.md`: before invoking codex, run
`scripts/risk_assess.py` on the frozen diff → tier → invoke
`codex exec -c model_reasoning_effort="$(…effort_for_tier…)"`. Default lands at
`medium` for the common low/medium diff; `xhigh` only on `critical`. The agent
already has the frozen diff, so no ticket-schema change is needed. The tier is
also written into the heartbeat (§4) and the review's `reviewer_meta` for audit.

## §3 Bounded codex + PM-managed escalation (NOT silent degrade)

Wrap the codex invocation in a portable timeout: a small Python wrapper
(`subprocess.run(..., timeout=N)`) — NOT a bare `gtimeout`, which is absent off
macOS-coreutils hosts. `N` is config (`codex_timeout_s` in `model-routing.yaml`,
default 240; retry budget 180), not hardcoded. On timeout:

1. retry **once** at one-lower effort (xhigh→high→medium→low);
2. still over budget → write a schema-valid `review.json` with `verdict: ABSTAIN`
   + a `reviewer_meta.abstain_reason: codex-timeout`. Codex is a second opinion,
   never a blocker (model-routing.md:34) — ABSTAIN means the PM accepts the Claude
   verdict and sees the full heartbeat trail to decide a manual re-run. Never an
   infinite hang; never a blind merge-block.

`schemas/review.schema.json` verdict enum is `[APPROVE, REJECT]` today → **add
`ABSTAIN`** (the only schema touch).

### §3a Evidence-gate reconciliation (cross-feature — REQUIRED)

The run-3 exit gate (`scripts/_evidence.py assert_round_evidence`, shipped
`56553e2`) requires BOTH reviewers' `review.json` to exist and be `APPROVE`. A
codex ABSTAIN would therefore be blocked by our own gate. Reconcile so the gate
distinguishes an **honest, evidence-rich ABSTAIN** from the run-3 **silent skip**:

- codex `review.json` PRESENT with `verdict: ABSTAIN` + `abstain_reason` →
  acceptable IFF the claude reviewer is `APPROVE`. (Codex ran, timed out, wrote an
  honest verdict + heartbeat trail — this is the opposite of the run-3 bypass,
  which was a MISSING ticket + EMPTY output dir.)
- codex `review.json` MISSING / empty / unparseable → still BLOCKED (unchanged —
  this is the run-3 hardening, kept intact).
- claude reviewer ABSTAIN is NOT accepted — the cold-Claude verdict is the
  load-bearing one; only the codex second-opinion may abstain.

`assert_round_evidence` gains an `allow_codex_abstain` branch keyed on
`verdict == "ABSTAIN" and abstain_reason present`; new unit tests cover both the
honest-ABSTAIN-pass and the still-blocked silent-skip.

## §4 Reviewer heartbeat (PM visibility)

Reviewers write `outputs/<role>/status.json` (`role`, `started_at`, `elapsed_s`,
`last_beat`, `phase`, `risk_tier`) at start and on each codex retry/transition.
New `orchestrator.py review-status` reads all reviewer status files for the
active round and prints a compact table; `agents/swarm-monitor.md` cites it so
"swarm health" surfaces in-flight reviewer progress. Mirrors the existing
worker-status pattern — no new schema beyond a documented shape.

## §5 Verifier-tier enforcement (accuracy)

New `hooks/verifier-tier-gate.sh` (PreToolUse Task): if `subagent_type` is in the
verifier/reviewer set (`auto-pilot-{codex,claude}-reviewer`, `review-gatekeeper`,
`swarm-verifier`, `tech-critic-lead`) AND a `model:` override is present in the
Task input that is BELOW `_routing.verifier_min_tier()`, deny with the routing
reason. Absent override (agent-frontmatter model wins) or at/above tier → allow.
Unparseable stdin → fail-open. Wire in `hooks/hooks.json`; `chmod +x`; script-style
self-test + wiring test.

## Error handling

Hooks deny via `permissionDecision` JSON, fail-open on unparseable stdin. Codex
timeout degrades to ABSTAIN (logged), never crashes the round. Missing
`model-routing.yaml` → `_routing` raises a clear error (fail-closed for the
resolver; the gate hook treats a resolver error as fail-open + stderr warn so a
config typo never bricks all dispatch).

## Testing

- `tests/test_routing.py` — `effort_for_tier` matrix (all 5 tiers + unknown),
  `verifier_min_tier`, missing-yaml error.
- `tests/test_evidence.py` (extend) — §3a: codex ABSTAIN+reason & claude APPROVE
  PASSES; codex ABSTAIN but claude REJECT/missing BLOCKS; codex missing/empty
  still BLOCKS (run-3 hardening intact); claude ABSTAIN never accepted.
- codex-effort selection — unit test the tier→effort wiring (mock risk tier).
- §3 timeout→retry→ABSTAIN — test the wrapper with a fake hanging command (sleep)
  → asserts one retry then ABSTAIN review.json.
- `hooks/test_verifier_tier_gate.py` — deny/allow matrix (under-tier verifier,
  at-tier, non-verifier, no override, unparseable).
- heartbeat read — `review-status` over fabricated status.json files.
- Full gate: pytest + mypy + ruff + shellcheck + module-size + doc-ref + the two
  new hook self-tests appended to the CLAUDE.md bundled chain.

## Residual risks (stated)

- The interactive PM dispatches reviewers via the **blocking** Agent tool, so the
  heartbeat is pollable mid-flight only in the headless/subprocess path or by a
  parallel monitor; in a single blocking Agent round the PM sees the trail on
  return, not live. Documented, not solved here.
- `_routing` resolver is intentionally narrow (no role×task matrix) — slice C
  will need a richer record shape; v1 does not pre-build it.
- §5 keys on a `model:` override in the Task input; a verifier whose frontmatter
  model is under-tier (not an override) is not caught by the hook — covered
  instead by the agent-contract audit, not this gate.
- ABSTAIN-on-timeout means a genuinely hung codex contributes no adversarial
  signal that round; the diff still gets the cold-Claude verdict + any specialists.

## Non-goals

No slice-C ledger/rebalance code (deferred spec). No new verifier agents (reuse
existing per model-routing.md:44). No worker-model routing changes. No
ticket-schema change (codex agent self-derives tier).

## Disposal

Shipped → distill the wiring into `docs/architecture.md` + keep
`model-routing.md`/`.yaml` as the living SoT; delete this design doc.
Slice-C gets its own spec citing this one.
