---
name: pm-quality-harness-loop
description: >-
  PM-orchestrated end-to-end codebase quality lift toward big-tech standard, then
  ships it. Use whenever the user wants to raise a repo's quality to a target band
  ("get this to big-tech 95", "quality lift", "코드 품질 빅테크로 올려줘", "score and
  fix this codebase then merge", "harden + ship this repo"), OR when they want the
  full lifecycle around a quality pass — not just scoring, but fixing across
  dimensions, an adversarial correctness bug-hunt, syncing the harness docs to the
  new gates, and an autonomous merge. This is the SUPERSET orchestrator: it composes
  auto-pilot:adversarial-review-loop (multi-agent mode for the dimension fan-out,
  branch mode for the bug-hunt) as its engine and adds the three things that engine
  lacks — a harness-doc-update phase, an autonomous-merge tail, and an HONEST
  definition-of-done (report the real weighted score, never a forced round number).
  Reach for this over plain adversarial-review-loop when the deliverable is "the repo
  is measurably better AND shipped AND its docs match", not just "a score" or "a
  reviewed branch". The PM (this session) dispatches subagents and does git-ops only —
  it does not edit code itself.
---

# PM Quality Harness Loop

A repeatable, PM-orchestrated flow that takes a repo from "current quality" to
"measurably better, correctness-verified, docs-synced, and merged" — and reports
the honest score it actually reached, not a number it was told to hit.

This skill is an **orchestrator**, not a scorer. The scoring + dim-fix + dual-track
review machinery already exists in `auto-pilot:adversarial-review-loop`. This skill
**composes** that engine and wraps it with the phases a real ship needs.

## When to use / not use

Use it when the deliverable is the *whole lifecycle*: lift quality across dimensions,
prove correctness, sync the harness docs, and ship. Triggers include "big-tech 95",
"quality loop then merge", "harden and ship this repo", "코드 품질 올리고 머지까지".

Do NOT reach here for the narrower jobs the sub-skills already own:
- Only want a score / 13-dim rubric pass → `auto-pilot:quality-eval`.
- Only want to fan out fixes + re-score (no doc-sync, no merge) → `auto-pilot:adversarial-review-loop` codebase/multi-agent mode directly.
- Only want a Codex×Claude review of a branch → `adversarial-review-loop` branch mode.
- Only want doc↔code drift fixed → `auto-pilot:doc-drift-audit`.
- Only want dead-code/residue removed → `residue-audit`.

The unique value here is *sequencing* those into one honest, shippable pass.

## The engine (reuse, do not rebuild)

`auto-pilot:adversarial-review-loop` is the engine. Cite it; do not duplicate its
rubric, dispatch, or cross-verify logic.

- **Dimension fan-out** = its **multi-agent mode** (or `codebase` mode if the repo is
  small / few contracts). Workers are worktree-isolated, dim-routed (Codex `codex exec`
  for type/test/perf/security; Claude `general-purpose` for refactor/docs/prose).
- **Adversarial bug-hunt** = its **branch mode** — two independent reviewers
  (Codex `codex exec -s read-only` + a cold Claude subagent) over the diff, cross-verified.
- **Scoring rubric** = `auto-pilot:quality-eval` (13 dims, weights, hard-fail rules,
  anti-inflation guard). The board is `.planning/quality/score-state.json`.

## The PM contract

The main session is the **PM**. The PM dispatches subagents and performs git-ops
(commits, branch, PR, merge, worktree cleanup) — but **does not edit code itself**,
except a small review-fix or the git mechanics. The PM reads worker *summaries* +
`score-state.json`, not full diffs/worktree files — this preserves PM context for the
long multi-phase run. (Token cost may rise; that is the trade for staying in control
across all phases. Speed/quality > token cost.)

Why no code edits: the PM is the integrator and the only one with the whole-repo view.
If it also writes code, it loses neutrality for review and burns the context the
orchestration depends on.

## Phases

Run them in order. Each phase gates the next. The whole point is that a clean
later phase is meaningless if an earlier one is faked.

### Phase 0 — Make CI a real gate FIRST

Before scoring anything, confirm the project's verification actually runs where it
claims to. The most common lie in a quality number is "tests pass" when they only
pass on the author's laptop — e.g. contract tests hard-pinned to a local path, or a
fixture/dependency the hosted runner never provisions.

- Run the repo's own verify entry point (e.g. `verify-harness.sh`, `make verify`, CI
  workflow locally). If it only passes locally, fix the portability gap (vendor a
  minimal fixture, de-hardcode paths, env-aware lookups) so the gate is faithful.
- If CI cannot run at all (billing block, no runner), say so explicitly and treat the
  local gate as the faithful one — but record that CI-on-runner is UNPROVEN; it
  becomes a residual in the DoD, not a silent pass.
- Why first: every later score and "green" claim rides on this. A skipped/unfaithful
  gate caps the `ci_cd` dimension at its hard-fail floor regardless of other work.

### Phase 1 — Dimension fix fan-out

Delegate to `adversarial-review-loop` multi-agent mode: ANALYZE → EVALUATE (dual-track,
Claude + Codex, lower-of-two wins) → APPROVE (human gate) → EXECUTE (worktree-isolated
workers, one contract each) → RESCORE → CHECK. Each worker proves its fix with the
*dimension's own* gate (type = mypy clean; test = coverage gate passes; perf = bench
compare gate; dead-code = 6-gate removal proof) — not a fabricated unit test.

Keep contracts small (≤4 findings, disjoint files) so parallel workers don't collide.
The PM serializes within a conflict group, parallelizes across groups.

### Phase 1.5 — Codex × Claude adversarial bug-hunt (correctness layer)

Dimension scores measure *shape*; they don't catch logic bugs. Add a correctness gate
on top via `adversarial-review-loop` branch mode over the full diff:

1. Spawn **two independent reviewers** in parallel: Codex (`codex exec -s read-only`,
   emits strict-JSON findings) and a **cold** Claude subagent (no implementation
   context). Each hunts logic errors, type lies, error-handling regressions, broken
   invariants, boundary/race bugs, security/gate weakening.
2. **Cross-verify**: a finding only becomes a fix ticket if both confirm it, OR one
   flags it and you read the cited code and confirm it real. Claude refutes Codex false
   positives; Codex surfaces what the rubric pass missed. Read the actual code before
   accepting any finding.
3. Fix confirmed findings RED→GREEN (testable) or with the proving gate (non-testable).
4. **Loop until two consecutive rounds surface zero new confirmed findings.** One clean
   round isn't convergence — the second confirms the fixes didn't open new holes.
5. **Whack-a-mole stop guard**: if the same finding survives 2 rounds, or reviewers
   contradict each other 3 rounds running, or you're playing deny-list whack-a-mole
   with no convergence — STOP and report "strategy change needed". Do not loop forever.

Run it again pre-merge if Phase 3/4 changed code.

### Phase 2 — Honest re-score vs DoD

Re-score with `quality-eval`, dual-track if possible (if the Codex eval track abstains —
e.g. empty output — say so; the Claude track stands, surface the abstention). Update
`score-state.json`: append the prior snapshot to `history[]`, record per-dim
`prev`/`delta`.

**Anti-inflation is mandatory**: any dimension that rose ≥5 must cite `file:line` +
commit SHA in its `notes`, else revert it to the prior value and log `inflation-blocked`.
Apply hard-fail caps honestly (a skipped CI gate caps `ci_cd` at 60 even if the wiring
is perfect — see Phase 0).

See **Honest Definition of Done** below for what "done" means.

### Phase 3 — Harness-doc sync (the differentiator)

After code is green, the harness docs are usually stale — they describe the old gates,
miss new knobs, or cite removed symbols. Sync them:

- Update the repo's harness docs (`.claude/{rules,architecture,runbooks}` + interface
  pages, project `CLAUDE.md`) to match the new code/gates. Every claim carries a
  `file:line` or ADR citation that actually resolves. New gates/knobs (a type checker,
  coverage floor, cost cap, env var) get documented where operators look for them.
- **Deep-module / interface convention**: one source of truth per fact; the other tree
  *cites* it — never duplicate the same fact in two docs (they drift apart).
- Any contract a Phase-1 fix changed gets a new or amended **ADR**.
- Run the repo's deterministic **drift / doc-link guard** (e.g. `drift-scan.sh`,
  `check_doc_links.py`). If the repo has no such guard, install one and wire it into the
  verify path — mechanical `file:line`-integrity checks are the only thing that keeps
  docs honest at scale. (Semantic drift is a separate, human/skill pass — see
  `doc-drift-audit`.)

Why this phase exists: a quality lift that leaves the docs lying is a regression in
the dimension that matters most for the *next* engineer. This is the phase the bare
review-loop engine does not have.

### Phase 4 — Verify + autonomous merge

1. Final faithful gate: full test suite + lint/type + drift-scan + verify-harness, all
   green locally (and CI-on-runner if available).
2. Single squash PR → main. PR body is the honest record: real weighted score (not a
   round number), the movers with evidence, and the **named residual risks**.
3. Merge per the project's policy. If CI cannot gate (billing/no-runner) and the project
   has an admin-merge precedent + standing authorization, admin-merge and say so plainly
   in the PR. Otherwise, stop at PR-created and hand the merge to the operator — do not
   bypass gates without authorization.
4. Tail cleanup: prune transient spec/plan docs per doc-lifecycle (durable content goes
   to ADRs/wiki first; verify no live links cite them — keep the ones an ADR still
   references). Remove leftover worktrees (`git worktree remove --force` + `prune`).
   Leave branch-ref deletion to the operator if a destructive-action guard blocks it —
   surface the branches, don't self-override the guard.

## Honest Definition of Done

DoD is *honest*, not a forced number. The skill is "done" when:

1. Every **fixable** dimension reaches its target band, proven by its own gate.
2. Two consecutive adversarial rounds find zero new confirmed findings.
3. The harness docs match the code (drift guard green).
4. The work is merged (or PR-created + handed off if merge isn't authorized).

Report the **real weighted score reached**. If the realistic ceiling is below the
aspirational target because some dimension is architecturally **frozen** (an accepted
ADR limit) or externally **blocked** (CI can't run), say so up front and name it. Never
inflate a dim to hit a round number; "95" or "92-94" is aspirational, and you state the
gap and *why* it exists. A truthful 86 beats a fabricated 95 every time — and the
conservative-eval rule requires it.

## Failure modes & stop guards

- **Worker blocked** → PM provides context or escalates model tier; never silent.
- **Adversarial whack-a-mole** (no convergence, deny-list churn) → STOP, report
  "strategy change needed".
- **CI red after a ticket** → debug systematically before any further fix; don't pile on.
- **Eval track abstains** (Codex empty output / malformed) → retry once, then the Claude
  track stands and you surface the abstention. Don't pretend you had two tracks.
- **gh account drift** → re-check the active account before every push/PR/merge; it can
  silently revert.
- **Worktree branches off a stale base** → run workers on a worktree explicitly created
  off current HEAD, or serially on the main tree; a stale-base worktree silently drops work.

## Cross-references

- `auto-pilot:adversarial-review-loop` — the engine (multi-agent dim fan-out + branch-mode bug-hunt). Cited, not duplicated.
- `auto-pilot:quality-eval` — the 13-dim rubric, weights, hard-fail + anti-inflation rules.
- `auto-pilot:doc-drift-audit` — semantic doc↔code drift (Phase 3 handles mechanical/known-gate drift; this handles unknown semantic drift).
- `residue-audit` — dead-code/duplicate removal (a Phase-1 dimension tool).
- `superpowers:verification-before-completion` — evidence-before-assertions discipline behind the honest DoD.
