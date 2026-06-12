---
name: adversarial-review-loop
description: >
  Dual-track review + improvement loop, three modes.
  **branch mode** (default): Codex + Claude independently review the working branch/PR, cross-verify findings, fix, re-review until both approve. Triggers: "adversarial review", "codex review loop", "review until approve", "이중 리뷰", "PR cross-review", risky PR pre-merge.
  **codebase mode**: scores the whole codebase on the quality-eval 13-dim rubric, fans out improvement contracts in parallel, re-scores until target. Triggers: "quality loop", "코드 품질 점수", "score this project", "95점", "빅테크 평가", "codebase quality improvement", "quality-eval". Supersedes quality-eval/quality-loop skills.
  **multi-agent mode** (opt-in dispatch layer on codebase mode): PM main session + dim-routed Codex/Claude worker pool + cold-Claude reviewer pool; activation-gated by repo size + contract count. Triggers: `mode=multi-agent`, `--multi-agent`, "multi-agent review", "pm-worker loop", "코덱스 워커 풀".
  **lifecycle mode** (superset orchestrator; absorbed pm-quality-harness-loop): whole-lifecycle quality lift then ship — CI-faithfulness gate → dimension fan-out → adversarial bug-hunt → honest re-score → harness-doc sync → autonomous merge. Use when the deliverable is "measurably better AND docs-synced AND merged", not just a score. Triggers: `mode=lifecycle`, `--lifecycle`, "big-tech 95", "quality lift then merge", "harden and ship", "코드 품질 빅테크로 올려줘", "score and fix this codebase then merge".
  Git-baseline hygiene checks (uncommitted/unpushed/stash/conflicts) every round.
  NOT for: dead-code/duplicate/stale-comment removal without a score target (residue-audit), doc↔code prose drift (doc-management), harness bootstrap (setup-harness), vault export/scoring (vault-build/vault-score) — route "코드 정리"/"clean up" requests to residue-audit unless the user asks for a score or a review verdict.
---

# Adversarial Review Loop (Codex × Claude)

Two independent reviewers, dual modes:

| Mode | Scope | Cycle | Exit |
|---|---|---|---|
| **branch** | working branch / single PR | review → fix → re-review | both reviewers approve |
| **codebase** | entire project tree | analyze → score → contracts → fan-out fix → re-score | weighted_score ≥ target (default 95) |
| **multi-agent** | codebase + PM-Worker dispatch | codebase mode + PM-routed worker pool | same as codebase + activation gate met |
| **lifecycle** | whole-lifecycle quality lift + ship | CI gate → dim fan-out → bug-hunt → re-score → doc-sync → merge | honest DoD (see Lifecycle mode) |

Codex catches what Claude misses, Claude catches Codex false positives, both catch git tangles.

## Mode selection

- User says "review this branch / PR" → **branch mode**
- User says "score this codebase / 95점 목표 / 품질 루프 / quality eval" → **codebase mode**
- User says "multi-agent / pm-worker / 코덱스 워커 풀" OR passes `--multi-agent` → **multi-agent mode** (after codebase mode activation gate, see below)
- User says "big-tech 95 / quality lift then merge / harden and ship / 품질 올리고 머지까지" OR passes `--lifecycle` → **lifecycle mode** (superset orchestrator, see Lifecycle mode at the end)
- Ambiguous → AskUserQuestion before round 1
- Args: `mode=branch|codebase|multi-agent|lifecycle`, `target=N`, `dimension=X`, `execution=sequential|parallel`, `max_workers=N`, `--multi-agent`, `--lifecycle`

## Codex invocation policy (token offload)

- Branch-mode reviewer = `/codex:adversarial-review` slash — UNCHANGED. This is the one dedicated dual-review path.
- All other Codex usage = direct `codex exec -c model_reasoning_effort=high -s workspace-write` via Bash, not `Agent(subagent_type=codex:codex-rescue)`.
- Rationale: `codex exec` offloads model tokens to Codex (gpt-5.x); Claude spawns it and reads only the result file / commit log.
- Offload point 1: codebase EVALUATE Track B runs `mkdir -p .planning/quality && codex exec -c model_reasoning_effort=high -s workspace-write "Score this codebase against the quality-eval 13-dim rubric. Write ONLY strict JSON to .planning/quality/eval-codex-{iteration}.json. Schema: object with all 13 canonical dim keys, each value {score:number, notes:string, hard_fail:boolean}. Inputs: .planning/quality/analysis-A.md, .planning/quality/analysis-B.md, .planning/quality/analysis-C.md, .planning/quality/score-state.json, and ../quality-eval/SKILL.md."`; Claude reads the JSON only. <!-- NOTE: ../quality-eval/SKILL.md is relative to this skill's directory; before spawning Codex, resolve it to an absolute path first (e.g. $(cd "$(dirname "$SKILL_FILE")/../quality-eval" && pwd)/SKILL.md) — Codex runs in a separate process with no plugin-relative cwd and cannot expand relative refs. -->
- Offload point 2: multi-agent Codex Worker runs Bash command `arl_worktree_ensure {slug} origin/main && codex exec -c model_reasoning_effort=high -s workspace-write "{worker_prompt}"` with no trailing `-`. Background exit re-invokes the harness.
- Codex worker commits + pushes `quality/{slug}`; PM reads `git log quality/{slug}` summary, never the diff.
- `.worktrees/` must be present in the repo's `.gitignore` before dispatch.
- Tradeoff: direct `codex exec` loses the structured Agent result object. Mitigate with structured artifacts (JSON for eval, commit+branch for workers) and short summaries only.
- Codex CLI hang risk still applies → keep hang→Claude-takeover fallback.
- **Sandbox policy**: every codex exec runs with `-s workspace-write` (NOT `--dangerously-bypass-approvals-and-sandbox`). Writable roots = cwd (the worktree) + system temp (`/tmp`). HOME, `~/.ssh`, `~/.codex/auth.json`, `/etc`, etc. are **blocked**. Workers stay scoped to their contract worktree by the sandbox itself, not just by prompt. Verified live: HOME-write attempt was refused with "outside the permitted writable roots".

## Command convention

- Backtick commands are templates the agent fills before running; never copy-paste literally.
- Known loop values use brace placeholders: `{slug}`, `{iteration}`, `{contract}`, `{dim}`, `{delta}`, `{base_ref}`, `{src_dir}`.
- Agent MUST fill `{worker_prompt}` before dispatch — never dispatch an empty prompt.

## Helpers (bash, tested)

- All shell logic lives in `scripts/arl-helpers.sh` (unit-tested by `tests/arl-helpers.bats` + `tests/arl-orchestration.bats`; count with `rg -c '^@test ' tests/*.bats`).
- **Always invoke under bash** (the helpers use bash arrays; sourcing into zsh — the macOS default — breaks them). Two ways: pure fns → `bash "$SKILL_DIR/scripts/arl-helpers.sh" <fn> <args>`; a chain that needs the worktree cwd → `bash -c '. "$SKILL_DIR/scripts/arl-helpers.sh"; arl_worktree_ensure <slug> origin/main && codex exec ... "<worker_prompt>"'`.
- Call helpers by NAME with real args — do NOT inline shell in this runbook. `{slug}`/`{iteration}`/`{src_dir}` are agent-substituted before the call.
- Verify helpers anytime: `bats "$SKILL_DIR/tests/arl-helpers.bats" "$SKILL_DIR/tests/arl-orchestration.bats"` (green = shell layer correct).
- Validated end-to-end on a live scratch repo: real codex worker fixed a seeded bug → cold review → `arl_local_merge` → main green → `arl_worktree_cleanup` (no orphans).
- Functions: `arl_conflict_markers [path]`, `arl_ahead_behind`, `arl_repo_size_ok <src_dir> [n]`, `arl_parse_scope_files <contract>`, `arl_contract_path <slug>`, `arl_conflict_groups [dir]`, `arl_worktree_ensure <slug> [base]`, `arl_worktree_cleanup <slug>`, `arl_pr_create_idempotent <slug> <contract> [base]`, `arl_local_merge <slug>`, `arl_approve_action <a|b|c|d>`, `arl_check_termination <weighted> <target> <viable> <iter> <max> <user_exit>`, `arl_activation_gate <requested> <src_dir> <open> <approved>`, `arl_dispatch_waves <contracts_dir> [n]`.

---

# branch mode

Two independent reviewers, per round, until both approve. Codex catches what Claude misses, Claude catches Codex false positives, both catch git tangles.

## Pre-flight

Session-once:

1. Verify codex plugin ready: run `/codex:setup`. If not ready, instruct user to install, then stop.
2. Confirm `/codex:adversarial-review` slash exists. If missing, abort.

Per-round baseline (START of EVERY round, including round 1):

1. Establish baseline:
   - `git fetch origin` — refresh remote refs before ahead/behind checks
   - `git status --short` — note uncommitted files
   - `arl_ahead_behind` — note upstream behind/ahead counts if available
   - `base_ref=$(gh pr view --json baseRefName -q '.baseRefName' 2>/dev/null | sed 's#^#origin/#'); [ -n "$base_ref" ] || base_ref=origin/main; git rev-parse --verify "$base_ref" >/dev/null || { printf '%s\n' "base_ref $base_ref missing; AskUserQuestion for review base." >&2; exit 1; }` — review base may not be `main`
   - `git stash list` — note any stash
   - `arl_conflict_markers .` — conflict markers
   - If WIP exists, ask user: stash and proceed, or commit first.
2. Print baseline summary table to user; confirm before Round 1.

## Round flow (repeat until exit)

Start each round by running the per-round baseline above. Then run **two independent review tracks in parallel**, merge findings, fix, and re-review.

### 1. Parallel review (initial)

**Risk gate first:** run `python3 scripts/risk_assess.py --diff-range {base_ref}..HEAD` (auto-pilot plugin root — resolve to an absolute path before running, same caveat as `../quality-eval/SKILL.md` above; advisory JSON, exit 0) and dispatch per its `review_policy`. Rule SoT = `agents/pm-orchestrator.md` § Token-efficiency rules (2026-06-07), rule a — the table below is dispatch shorthand, not a second definition; tier/policy tokens are defined in `scripts/risk_assess.py` only.

| `review_policy` | tracks to spawn |
|---|---|
| `skip-review` | none — ONLY if tier is `none` AND no hook/schema/script files (`hooks/`, `schemas/`, `scripts/`) in the diff; else `single-reviewer` minimum |
| `single-reviewer` | ONE track (alternate codex/claude across rounds/contracts) |
| `dual-review` | both tracks below (default) |
| `dual-review+gatekeeper(security mode)+tight-rescope` | both tracks + security-mode gatekeeper + per-finding tight re-scope |

PM may override upward, never below the tool's tier without recorded cause (see SoT).

For `dual-review` (default), spawn both at once in a single message:

- **Codex track**: `/codex:adversarial-review --base {base_ref}` (background if diff is large, foreground if small).
- **Claude track**: independent self-review. Use the `/review` slash skill, OR spawn a `general-purpose` Agent with a strict reviewer prompt. The reviewer must NOT have seen the implementation reasoning — it reviews the diff cold. Pass: branch, base ref, focus hints.

Reviewer prompt template for Claude track:

```
Cold review of `git diff {base_ref}...HEAD`. You did not write this code.
Look for: bugs, race conditions, security holes, broken invariants,
off-by-one, error-handling gaps, schema/contract drift, test gaps,
git history weirdness (force-push artifacts, lost commits, merge
fragments). Report: verdict ∈ {approve, needs-attention} and a list
of findings with file:line + evidence.
```

### 2. Findings merge

Build a single table:

| # | File:Line | Codex | Claude | Triage |
|---|-----------|-------|--------|--------|
| 1 | path:42 | ✓ | ✓ | confirmed-real |
| 2 | path:88 | ✓ | – | needs-cross-verify |
| 3 | path:120 | – | ✓ | needs-cross-verify |
| 4 | path:200 | ✓ | ✓ | pre-existing (not in diff) |

Triage rules:
- **Both flag** → confirmed real, fix.
- **One flags** → read the cited code yourself, decide. If real, fix. If false positive, draft a rebuttal citing exact lines + behavior; pass back to that reviewer next round.
- **Pre-existing** (not introduced by this branch's diff) → log separately, do not block approval. Surface to user.

### 3. Fix (RED→GREEN or targeted gate)

Classify each confirmed finding:

| Class | Examples | Verification |
|---|---|---|
| Testable | logic bug, race, off-by-one, contract/schema drift, error-handling | service-level RED→GREEN test |
| Non-testable | documentation drift, naming, dead code, comments, formatting, log redaction | targeted gate that proves the fix |

For testable findings:
1. Write a failing test at the **service level** (endpoint mocks break easily — prefer real DB / real client where the project allows it).
2. Run test → confirm RED.
3. Fix code.
4. Run test → confirm GREEN.
5. Run full project test suite — no regressions.

For non-testable findings:
1. Make the change.
2. Run the targeted gate: dead code = 6-gate removal proof; documentation = drift-check / signature match; security log redaction = assertion that formatted output contains no secret; naming/formatting = lint/AST gate pass.
3. Acceptance = the gate that actually proves the fix.

Cross-repo finding (e.g. backend ↔ web)? Patch both sides in the same round.

### 4. Parallel re-review (scoped — fix commits only)

Round N+1 reviews ONLY the fix commits since round N's reviewed diff — record `prev_head=$(git rev-parse HEAD)` when round N's reviewers are dispatched; the re-review input = `git diff {prev_head}..HEAD`, NOT the whole branch diff re-frozen. Full-branch re-review only when (a) a fix touched >30% of the original scope files, or (b) a reviewer requests it with stated cause. (Scope-contraction rule SoT: `agents/pm-orchestrator.md` § Token-efficiency rules, rule b.)

Spawn the same tracks as step 1 (per `review_policy`) over that fix diff, with focus hint:
> "Round N. Previous findings fixed: [list]. Verify the fixes are correct and complete. Look for new issues introduced by the fixes — in these hunks."

### 5. Verdict gate

Exit only when **both tracks return approve**.

| Codex | Claude | Action |
|-------|--------|--------|
| approve | approve | exit, commit + push, CI watch |
| approve | needs-attention | next round (Claude-side findings) |
| needs-attention | approve | next round (Codex-side findings) |
| needs-attention | needs-attention | next round, full triage |

### 6. Commit + push

Once both approve:
- Commit per logical fix (not one giant commit). Conventional Commits.
- Push (PR auto-merge policy per project).
- `gh run watch` until CI green.

## Termination

Exit conditions (any one):
- Both reviewers approve **and** CI green.
- User says stop.
- Same finding survives 2 consecutive rounds (fix is not landing — escalate to user, do not loop).
- Disagreement loop: 3 consecutive rounds where reviewers contradict each other on same finding (escalate).
- Round 5+: ask user "another round worth it?" before continuing.

## Guardrails

- **Never** `git reset --hard`, `git push --force` to main/master, `git checkout --` on dirty tree, `git clean -f`, or `git branch -D` without explicit user approval.
- Use `git reset --soft` and `--force-with-lease` for feature branches when needed.
- Never `--no-verify` on commits.
- WIP working tree → `git stash push -u -m "review-loop-round-N"`. Restore at exit.
- Pre-existing breakage stays separate from finding list (it's not your branch's fault).
- Tests at service level by default. Endpoint mocks only when service-level is impossible.
- LLM-side validation: N≥2 runs before claiming an LLM-related finding is fixed.

## Round summary format

After every round, print this table to the user:

```
Round N — Verdict: codex=<v>, claude=<v>
Findings:
| # | file:line | who | severity | action | status |
|---|-----------|-----|----------|--------|--------|
| 1 | ... | both | high | RED→GREEN | fixed |
| 2 | ... | codex | med | rebut | rebutted |
| 3 | ... | claude | low | pre-existing | logged |
Tests: <added>, suite: <pass/fail>
Git: branch=<x>, ahead=<n>, behind=<n>, CI=<status>
Next: round N+1 OR exit
```

## Cross-repo (backend ↔ web)

If finding spans repos:
1. Identify both touchpoints (contract, schema, RPC, API).
2. Patch in lockstep — never merge one side first.
3. Both repos pass their own review loop.
4. Run integration smoke (real endpoints, not mocks) before declaring fix.

## Anti-patterns to avoid

- Single-track review (one reviewer alone) — defeats the cross-verify point.
- Accepting a finding without reading the cited code.
- Fixing pre-existing breakage inside this loop (scope creep — file separately).
- Squashing all rounds into one commit (history loses the "why").
- Skipping baseline check at round start (git tangles compound silently).
- Force-push to land "clean" history during a review loop (destroys the audit trail you just built).
- Fabricating a meaningless unit test for a non-testable finding — use the proving gate instead.

## Quick mode

If user says "quick review" or branch is tiny (<10 lines diff):
- Single round, foreground both tracks, no test scaffolding for trivial typo/comment changes.
- Still require both-approve gate.

---

# codebase mode

> Scores entire project tree against the 13-dimension rubric in `../quality-eval/SKILL.md` (co-bundled sibling skill), fans out improvement contracts in parallel, and re-scores until target hit. Replaces standalone `/quality-loop` and `/quality-eval` skill paths.

## Inputs (args or AskUserQuestion)

| Flag | Default | Description |
|---|---|---|
| `target` | 95 | weighted score floor for DONE |
| `dimension` | (all) | focus single dim (e.g. `error_handling`, `performance_budget`) |
| `execution` | `sequential` | `sequential` (PR-by-PR) or `parallel` (fan-out, conflict risk) |
| `max_workers` | auto | optional cap for parallel fan-out |
| `max_iterations` | 10 | safety cap |

State file: `{cwd}/.planning/quality/score-state.json` — resumable.

Project configuration: `{cwd}/.quality-loop.json` (optional) — overrides language detection, lint/type/test cmd, src/test/exclude patterns. Falls back to language auto-detect (pyproject.toml / package.json / go.mod / Cargo.toml).

## State machine

```
INIT → ANALYZE → EVALUATE → APPROVE → EXECUTE → RESCORE → CHECK → (ANALYZE | DONE)
```

### Step 0 — INIT

1. Detect language (file fingerprints).
2. Load `.quality-loop.json` if present; else apply language defaults from `quality-eval` skill section 1+2.
3. If `score-state.json` exists, `AskUserQuestion`: resume or fresh.
4. Initialize state with `target`, `mode`, `focus_dimension`, `iteration=0`.

### Step 1 — ANALYZE (3 parallel Agents)

Spawn 3 read-only analysis agents in a single message:

- **Agent A — error_handling + async_correctness + performance_budget** → `.planning/quality/analysis-A.md`
- **Agent B — test_quality + type_safety + llm_prompt_quality** → `.planning/quality/analysis-B.md`
- **Agent C — logging + configuration + architecture + code_structure + documentation + security + ci_cd_quality** → `.planning/quality/analysis-C.md`

Each emits a findings table (Severity / File:Line / Issue / Fix Sketch / Dim Delta) + per-dimension score estimate.

Wait for all 3 before continuing.

### Step 2 — EVALUATE (Dual-track, mandatory)

Two independent scoring tracks run in parallel — never single-track in codebase mode.

**Track A — Claude eval Agent**: reads analysis-A/B/C.md + current `score-state.json`. Applies `quality-eval` rubric strictly (incl. Hard-fail rules, Penalty calibration, Anti-inflation guard).

**Track B — Codex eval (`codex exec`)**: Bash runs `mkdir -p .planning/quality && codex exec -c model_reasoning_effort=high -s workspace-write "Score this codebase against the quality-eval 13-dim rubric. Write ONLY strict JSON to .planning/quality/eval-codex-{iteration}.json. Schema: object with all 13 canonical dim keys, each value {score:number, notes:string, hard_fail:boolean}. Inputs: .planning/quality/analysis-A.md, .planning/quality/analysis-B.md, .planning/quality/analysis-C.md, .planning/quality/score-state.json, and ../quality-eval/SKILL.md."` with the same inputs but no view of Track A's output. Codex scores independently with the same rubric and writes `.planning/quality/eval-codex-{iteration}.json`. <!-- NOTE: ../quality-eval/SKILL.md must be resolved to an absolute path before the Codex prompt is assembled — Codex runs in a separate process with no plugin-relative cwd. Use: $(cd "$(dirname "$SKILL_FILE")/../quality-eval" && pwd)/SKILL.md -->

Track B output contract (strict):

```json
{
  "<dim_slug>": {
    "score": 0,
    "notes": "<file:line evidence>",
    "hard_fail": false
  }
}
```

JSON MUST include all 13 canonical dims: `type_safety`, `test_quality`, `error_handling`, `code_structure`, `configuration`, `logging`, `async_correctness`, `documentation`, `security`, `architecture`, `performance_budget`, `llm_prompt_quality`, `ci_cd_quality`.

**Reconcile**: Eval coordinator merges both:
- Per-dimension: lower of the two scores wins (strict ≠ nice).
- If gap > 10 between tracks on one dim → AskUserQuestion (use lower / use Claude / use Codex / rerun both tracks), then continue with the chosen value.
- Hard-fail flags from either track propagate to final score.
- Reconcile reads Track B JSON. Missing/malformed → retry Codex eval ONCE with schema reminder. Still malformed → Track B ABSTAINS, Claude track score stands, and abstention is surfaced to user.

Produces:

1. Per-dimension score (verified by 2 tracks, not estimated).
2. Weighted total: `Σ(score × weight)`.
3. Contracts (one file per fix) under `.planning/quality/contracts/contract-{NNN}-{slug}.md`, sorted by ROI = `(dim_delta × weight) / effort_level` (LOW=1, MED=2, HIGH=3). Each contract file MUST include `scope_files:` (list of files it will touch).
4. `eval-report-{iteration}.md` with grade table (A≥90, B80-89, C70-79, D60-69, F<60) + dual-track diff column.

**Anti-inflation enforcement**: any dim with ≥+5 vs previous iteration must cite file:line + commit SHA in `notes`. Missing citation → score reverted to previous value; history records `inflation-blocked`.

**Hard-fail enforcement (per quality-eval rubric Hard-fail rules)**: if mypy/ruff/test/coverage/secret/AST/CI gates fail at evaluation time, the relevant dim is capped at 60 regardless of other evidence.

### Step 3 — APPROVE (human gate)

`AskUserQuestion` with contract table:

```
Iteration {N}: {weighted}/100 → target {target} (gap {gap})
{K} contracts, projected score {weighted + Σ(delta × weight)}.

a) approve all
b) select IDs (e.g. 001,003,005)
c) skip remaining contracts this iteration (go to RESCORE)
d) exit loop
```

Choice → action via `arl_approve_action <choice>` (`c` = `skip_to_rescore`, NOT terminal; `d` = `exit_loop`).
Approved contracts → status `approved`, queued for EXECUTE. Option `c` queues no contracts; proceed to RESCORE, then CHECK.

### Step 4 — EXECUTE

For each approved contract (parallel if `execution=parallel`, sequential otherwise):

1. Sequential execution: PM may run `git fetch origin main && git switch -c quality/{slug} origin/main` in the main tree, one contract at a time.
2. Parallel execution: PM must NOT checkout in the main tree. One working tree cannot hold N branches — parallel REQUIRES per-worker worktree.
3. Pre-dispatch gate: `grep -qxF '.worktrees/' .gitignore || { printf '%s\n' '.worktrees/ missing; AskUserQuestion before dispatch.' >&2; exit 1; }`; add `.worktrees/` only after user approval, before first worker worktree setup.
4. Dispatch worker. Sequential may use main tree; parallel uses per-worker worktrees: Claude Agent via `isolation: worktree`; Codex Bash via `arl_worktree_ensure {slug} origin/main && codex exec -c model_reasoning_effort=high -s workspace-write "{worker_prompt}"`. Each worktree creates or reuses its `quality/{slug}` branch and asserts it before running.
5. Worker reads contract file → implements Fix Specification → runs lint/type/test → commits with `quality: {slug} [{dim} +{delta}pts]` → pushes `quality/{slug}`.
6. After worker completes: verify Acceptance Criteria, then `arl_pr_create_idempotent {slug} "$(arl_contract_path {slug})" main`.
7. Sequential execution: wait for merge before next contract. Parallel execution: dispatch only contracts cleared for parallel safety, then reconcile at end.

Failure handling: on verification fail, `AskUserQuestion` (skip / manual fix / pause). Never `--no-verify`.

Worker acceptance:
- Testable findings (logic bug, race, off-by-one, contract/schema drift, error-handling) require service-level RED→GREEN.
- Non-testable findings (documentation drift, naming, dead code, comments, formatting, log redaction) require the targeted gate that proves the fix.
- Acceptance = the gate that actually proves the fix; fabricating a meaningless unit test is forbidden (see anti-patterns).

### Worker prompt requirements (mandatory)

Every dispatch prompt MUST include (real-run #1 retro, 2026-05-22):

1. **Step 0 location check** — first worker action = mode-aware guard. Worktree-isolated dispatch (`execution=parallel` or `mode=multi-agent`): run `pwd`; Claude Agent worker (`isolation: worktree`) must pass `case "$(pwd)" in */.claude/worktrees/agent-*) : ;; *) echo "not in agent worktree" >&2; exit 1;; esac`; Codex Bash worker (`codex exec`) output must end in `.worktrees/quality-{slug}`; ABORT if `pwd` is the main repo root. Sequential main-tree dispatch: do not check `pwd`; run `git branch --show-current` and assert it equals `quality/{slug}`; ABORT if it is `main` or `master`. Prevents worktree-confusion (5/6 workers in real-run #1 defaulted to absolute paths in main repo unless explicitly anchored; recovery costs ~3 min/worker).
2. **File-size self-check** — after any new module add, `wc -l` to confirm ≤ project hard cap (default 500). If a new file would exceed cap, worker must split into siblings BEFORE commit (not after hook rejection).
3. **Contract complexity cap** — ≤ 4 distinct findings per contract; if contract touches ≥ 5 disjoint files OR spans 3+ layers, split into sub-contracts BEFORE dispatch.
4. **Local-merge fallback** — if `gh pr merge` is blocked (GH Actions billing, approval-token hook), worker reports the block; PM may perform board/merge git-ops (allowed, distinct from code edits) and falls back: `arl_local_merge {slug}`. Skip the PR UI; the audit trail lives in the commit log.

### Step 5 — RESCORE

Re-run rubric on current code. Update `scores`, append previous snapshot to `history[]`. Recompute `weighted_score`.

### Step 6 — CHECK termination

`arl_check_termination {weighted} {target} {viable_count} {iteration} {max_iterations} {user_exit}` → `DONE:<reason>` | `CONTINUE`.

Helper result is source of truth. Display reasons:
- `target_met` → DONE: `weighted ≥ target`
- `plateau` → DONE: 0 viable contracts (`delta ≥ 2`)
- `max_iterations` → DONE: safety cap
- `user_stop` → DONE: user `d` only (`user_exit=1`; `c` continues)

Else: `iteration++`, loop to Step 1.

## codebase mode guardrails

- Architecture-boundary contracts must show AST-test pass before PR (no shallow wrappers).
- `execution=parallel` is only safe when contracts touch disjoint files; in doubt, default sequential.
- Score never decreases without rationale — if RESCORE regresses, abort iteration and surface to user.
- Do not edit production code on branch `main` — always feature branch.
- Rule pages (`.claude/rules/*.md`) stay ≤80 lines; if rubric adds a gate, prove the gate is enforceable.

## Anti-patterns (codebase mode)

- "Just bump the score by tweaking weights" — weights are fixed in rubric.
- "Stub a test to satisfy coverage" — Acceptance Criteria requires real assertions.
- "Fake RED→GREEN for non-testable work" — use the targeted proving gate.
- "Squash 10 contracts into 1 PR" — granular PRs preserve history and rollback path.

---

# multi-agent mode

> Opt-in dispatch layer on top of codebase mode. The main-session PM (dispatch, board read, user gate, **no code edits**) + hybrid Worker pool (dim-routed Codex CLI `codex exec` / Claude general-purpose) + Reviewer pool (cold Claude). Reuses codebase-mode state, contracts, rubric, RESCORE, CHECK — replaces ONLY Step 4 EXECUTE.

## Activation gate

Evaluate with `arl_activation_gate {requested} {src_dir} {open_contracts} {approved}` → `MULTI_AGENT` | `FALLBACK`.

The function requires all three:

1. User passes `mode=multi-agent` OR `--multi-agent` flag OR explicit trigger ("multi-agent review", "pm-worker loop", "코덱스 워커 풀")
2. Repo size: after resolving `src_dir` below, `arl_repo_size_ok {src_dir} 200` OR open contracts ≥ 5
3. Approved contracts (from codebase Step 3) ≥ 3

`{src_dir}` = `src` glob from `.quality-loop.json` if present; else language-default source root from quality-eval detection (Python/JS: `app/` or `src/`; Go: `cmd/` + `internal/`; Rust: `src/`).

Below gate → fall back to codebase mode `execution=parallel` (or `execution=sequential`). Multi-agent skipped.

## Roles (2-tier, NOT 3-tier)

| Role | Model | Tool | Allowed |
|---|---|---|---|
| **PM** | main session (operator-selected model) | direct | board read, dispatch, user gate, final summary. **Zero code edits except user-explicit escalation.** |
| **Worker** | Codex 5.5 xhigh | `Bash(codex exec -c model_reasoning_effort=high -s workspace-write, run_in_background=true)` | code edits, test, lint, commit, PR |
| **Worker** | Claude Sonnet | `Agent(subagent_type=general-purpose, run_in_background=true)` | same; used for architecture/documentation contracts + Codex hang fallback |
| **Reviewer** | Claude (cold) | `Agent(subagent_type=general-purpose)` | diff-only cold review, verdict + findings |

**Reviewer = same Agent type as Claude worker, distinguished by prompt.** No separate hire/pool sizing. **PM constraint**: reads worker **summary** (≤10 lines + commit SHA) + `score-state.json` only — never diffs or worktree files. Board updates, PR, merge, cleanup git-ops allowed; code edits are not. (Total tokens may RISE — multi-agent trades total-cost for PM context preservation.)

## Worker routing (deterministic)

| Contract `dim` | Worker | Rationale |
|---|---|---|
| `type_safety`, `test_quality`, `error_handling`, `async_correctness`, `performance_budget`, `security`, `ci_cd_quality` | Codex | code-edit strong |
| `code_structure`, `configuration`, `logging`, `documentation`, `architecture`, `llm_prompt_quality` | Claude | refactor/prose strong |
| Worker hangs 1x (no commit, deadline elapsed) | Claude takeover | hang fallback per memory `feedback_codex_cli_hang_pattern` (project-scoped memory; if absent, the inline rule applies: 1st hang on a contract → Claude takeover) |

Fallback: unrecognized `dim` → default to Claude general-purpose worker and log a warning that the dim slug is off-canonical.

## Board = filesystem (no separate state file)

- `.planning/quality/contracts/contract-NNN-*.md` = ticket
- `git branch --list 'quality/*'` = in-progress
- merged PR (`gh pr list --state merged --head quality/{slug} --json number,headRefName`) = done
- `.planning/quality/score-state.json` = score history (shared with codebase mode; add `mode: "multi-agent"` field for this run's snapshots)

No `board.json` schema. Filesystem encodes state.

## Round flow (replaces codebase Step 4 EXECUTE)

```
1. PRE-DISPATCH gate (PM)
   - Confirm activation gate (above)
   - Verify ignore gate: `grep -qxF '.worktrees/' .gitignore || { printf '%s\n' '.worktrees/ missing; AskUserQuestion before dispatch.' >&2; exit 1; }`; add `.worktrees/` only after user approval, before dispatch.
   - `arl_dispatch_waves .planning/quality/contracts {N_workers}` → prints `wave K: <slugs>`.
   - Guarantee: serialize within conflict group, parallel across groups, capped per wave.
2. DISPATCH wave (single PM message, ≤N tool blocks)
   - Worker selection per routing table
   - Select at most one ready contract per conflict group, up to `N_workers` total; same-group contracts wait for later waves.
   - Codex command: `arl_worktree_ensure {slug} origin/main && codex exec -c model_reasoning_effort=high -s workspace-write "{worker_prompt}"`
   - Dispatch that command via Bash with `run_in_background=true`.
   - `{worker_prompt}` = contract path + Acceptance Criteria + "self-verify (lint/type/test) before reporting + commit + push" + Worker prompt requirements above.
   - Codex command creates or reuses/enters `.worktrees/quality-{slug}` at repo root before `codex exec` and passes the worker prompt as a positional argument.
   - Claude tool blocks: Agent(..., isolation="worktree", run_in_background=true)
   - Worker prompt: contract path + Acceptance Criteria + "self-verify (lint/type/test) before reporting + commit + push" + **Worker prompt requirements above (Step 0 location / file-size / complexity / merge fallback)**
   - PM MUST arm a fallback deadline wakeup at dispatch (~600s); otherwise an all-workers-hang deadlocks the loop.
3. WAIT (no polling; fallback deadline armed)
   - PM returns control to harness. Notifications fire on worker completion.
   - Between notifications PM may do unrelated work OR idle; deadline wakeup runs STUCK detection even with zero completions.
4. ON-NOTIFICATION (per worker, harness re-invokes PM)
   - After worker reports success and before Reviewer: `arl_pr_create_idempotent {slug} "$(arl_contract_path {slug})" main`
   - If PR creation is blocked, spawn cold Reviewer Agent to review `git diff origin/main...quality/{slug}`; PM acts on verdict, then uses local-merge fallback above if approved.
   - Spawn Reviewer = Agent(general-purpose) with cold prompt, diff via gh CLI
   - Reviewer verdict ∈ {approve, needs-attention}
   - approve → board update (merge PR per project policy). Codex Bash worker cleanup: `arl_worktree_cleanup {slug}`. Claude Agent worker cleanup: harness-managed; no manual remove.
   - needs-attention → re-dispatch SAME contract to SAME worker with reviewer findings (1 retry only). Second needs-attention after that retry → AskUserQuestion (skip / manual fix / split contract / pause).
5. STUCK detection (notification OR fallback deadline wakeup — use git evidence)
   - PM MUST arm a fallback deadline wakeup at dispatch; otherwise an all-workers-hang deadlocks the loop.
   - On every PM notification or deadline wakeup, scan: for each dispatched-but-not-completed worker,
     does `git log quality/{slug}` show ≥1 new commit since dispatch?
   - No commit + wall-clock since dispatch > 600s → mark `codex-hang` candidate
   - 1st hang same contract → auto-redispatch to Claude worker
   - 2nd hang same contract → AskUserQuestion (skip / manual / pause)
6. RESCORE → CHECK (delegate to codebase Step 5-6)
7. FINAL SUMMARY (PM emits, format below)
```

## Pool sizing

- CPU_cores = `getconf _NPROCESSORS_ONLN` (portable) or `sysctl -n hw.ncpu` on macOS.
- N_workers = `min(N_approved_contracts, 5, CPU_cores, max_workers if set)`
- Reviewer count = `ceil(N_workers / 2)`; reviewers are general-purpose Agents, drawn on demand, not pre-allocated
- Each wave dispatches at most ONE ready contract per conflict group, up to `N_workers` total, in one PM message; same-group contracts run in later waves.

## Final summary format (PM → user)

```
Round N — multi-agent
| # | Contract | Worker | Verdict | Commit | Dim Δ |
|---|----------|--------|---------|--------|-------|
| 1 | 001-foo  | codex  | approve | abc123 | code_structure +4 |
| 2 | 002-bar  | claude | approve | def456 | documentation +3 |
Score: {before} → {after} (Δ +{n}) | Hangs: {k}, Retries: {r}, Escalations: {e} | PM read audit: {diff_or_worktree_reads}=0
```

**Rollback:** Each contract = its own PR + commit. Bad merge → `pr_number=123; gh pr revert "$pr_number"`. No special rollback machinery; project's PR policy handles it.

## Validation criteria + Anti-patterns (multi-agent mode)

See `references/multi-agent-validation.md` — 5-criterion promotion gate table (PM read-isolation, Codex SPOF, orphan cleanup, merge-conflict, round-count) + full anti-pattern list. ABSTAIN policy for criterion #2 documented there.

---

# Lifecycle mode (--lifecycle)

> **Provenance: absorbed pm-quality-harness-loop 2026-06-07.** This mode folds the former `pm-quality-harness-loop` orchestrator into ARL verbatim. Use it when the deliverable is the *whole lifecycle* — not just a score or a reviewed branch, but "measurably better AND correctness-verified AND docs-synced AND shipped". Triggers: `mode=lifecycle`, `--lifecycle`, "big-tech 95", "quality lift then merge", "harden and ship", "코드 품질 빅테크로 올려줘", "score and fix this codebase then merge".

Lifecycle mode is a **superset orchestrator**: it composes the other ARL modes as its engine (codebase/multi-agent mode = dimension fan-out; branch mode = adversarial bug-hunt; the `quality-eval` rubric = scoring) and adds the four lifecycle phases those modes lack — a CI-faithfulness gate up front, a harness-doc-sync phase, an honest definition-of-done, and an autonomous merge tail. The main session is the **PM**: it dispatches subagents and performs git-ops (commit, branch, PR, merge, worktree cleanup) but **does not edit code itself** (except a small review-fix or git mechanics).

## When to use / not use (lifecycle)

Use it when the deliverable is the whole lifecycle: lift quality across dimensions, prove correctness, sync the harness docs, and ship. Do NOT reach here for the narrower jobs the other modes/skills already own:

- Only want a score / 13-dim rubric pass → `auto-pilot:quality-eval` (the rubric SoT).
- Only want to fan out fixes + re-score (no doc-sync, no merge) → ARL **codebase / multi-agent mode** directly.
- Only want a Codex×Claude review of a branch → ARL **branch mode**.
- Only want doc↔code drift fixed → `auto-pilot:doc-management` (AUDIT → MAINTAIN).
- Only want dead-code/residue removed → `auto-pilot:residue-audit`.

The unique value here is *sequencing* those into one honest, shippable pass.

## The engine (reuse, do not rebuild)

- **Dimension fan-out** = ARL **multi-agent mode** (or **codebase mode** if the repo is small / few contracts). Workers are worktree-isolated, dim-routed (Codex for type/test/perf/security; Claude for refactor/docs/prose).
- **Adversarial bug-hunt** = ARL **branch mode** — two independent reviewers (Codex `codex exec -s read-only` + a cold Claude subagent) over the diff, cross-verified.
- **Scoring rubric** = `auto-pilot:quality-eval` (13 dims, weights, hard-fail rules, anti-inflation guard). The board is `.planning/quality/score-state.json`.

## The PM contract (lifecycle)

The PM dispatches subagents and performs git-ops but **does not edit code**, except a small review-fix or the git mechanics. The PM reads worker *summaries* + `score-state.json`, not full diffs/worktree files — this preserves PM context for the long multi-phase run. (Token cost may rise; that is the trade for staying in control across all phases. Speed/quality > token cost.) Why no code edits: the PM is the integrator and the only one with the whole-repo view; if it also writes code it loses neutrality for review and burns the context the orchestration depends on.

## Phases (run in order; each gates the next)

A clean later phase is meaningless if an earlier one is faked.

### Phase 0 — Make CI a real gate FIRST

Before scoring anything, confirm the project's verification actually runs where it claims to. The most common lie in a quality number is "tests pass" when they only pass on the author's laptop — e.g. contract tests hard-pinned to a local path, or a fixture/dependency the hosted runner never provisions.

- Run the repo's own verify entry point (e.g. `verify-harness.sh`, `make verify`, CI workflow locally). If it only passes locally, fix the portability gap (vendor a minimal fixture, de-hardcode paths, env-aware lookups) so the gate is faithful.
- If CI cannot run at all (billing block, no runner), say so explicitly and treat the local gate as the faithful one — but record that CI-on-runner is UNPROVEN; it becomes a residual in the DoD, not a silent pass.
- Why first: every later score and "green" claim rides on this. A skipped/unfaithful gate caps the `ci_cd` dimension at its hard-fail floor regardless of other work.

### Phase 1 — Dimension fix fan-out

Delegate to ARL **multi-agent mode**: ANALYZE → EVALUATE (dual-track, Claude + Codex, lower-of-two wins) → APPROVE (human gate) → EXECUTE (worktree-isolated workers, one contract each) → RESCORE → CHECK. Each worker proves its fix with the *dimension's own* gate (type = mypy clean; test = coverage gate passes; perf = bench compare gate; dead-code = 6-gate removal proof) — not a fabricated unit test. Keep contracts small (≤4 findings, disjoint files) so parallel workers don't collide. The PM serializes within a conflict group, parallelizes across groups.

### Phase 1.5 — Codex × Claude adversarial bug-hunt (correctness layer)

Dimension scores measure *shape*; they don't catch logic bugs. Add a correctness gate on top via ARL **branch mode** over the full diff:

1. **Risk gate first:** `python3 scripts/risk_assess.py --diff-range {base}..HEAD` → dispatch per `review_policy`, same gate + policy table as branch mode §1 (rule SoT = `agents/pm-orchestrator.md` § Token-efficiency rules; skip guard included). Then, for the default `dual-review` policy, spawn **two independent reviewers** in parallel: Codex (`codex exec -s read-only`, strict-JSON findings) and a **cold** Claude subagent (no implementation context). Each hunts logic errors, type lies, error-handling regressions, broken invariants, boundary/race bugs, security/gate weakening.
2. **Cross-verify**: a finding only becomes a fix ticket if both confirm it, OR one flags it and you read the cited code and confirm it real. Read the actual code before accepting any finding.
3. Fix confirmed findings RED→GREEN (testable) or with the proving gate (non-testable).
4. **Loop until two consecutive rounds surface zero new confirmed findings.** One clean round isn't convergence — the second confirms the fixes didn't open new holes. Re-review rounds are scoped to the fix commits only (branch mode §4 scope-contraction; full re-review only on >30% scope touch or reviewer-stated cause).
5. **Whack-a-mole stop guard**: if the same finding survives 2 rounds, or reviewers contradict each other 3 rounds running, or you're playing deny-list whack-a-mole with no convergence — STOP and report "strategy change needed". Do not loop forever.

Run it again pre-merge if Phase 3/4 changed code.

### Phase 2 — Honest re-score vs DoD

Re-score with `quality-eval`, dual-track if possible (if the Codex eval track abstains — e.g. empty output — say so; the Claude track stands, surface the abstention). Update `score-state.json`: append the prior snapshot to `history[]`, record per-dim `prev`/`delta`. **Anti-inflation is mandatory**: any dimension that rose ≥5 must cite `file:line` + commit SHA in its `notes`, else revert it to the prior value and log `inflation-blocked`. Apply hard-fail caps honestly (a skipped CI gate caps `ci_cd` at 60 even if the wiring is perfect — see Phase 0). See **Honest Definition of Done** below for what "done" means.

### Phase 3 — Harness-doc sync (the differentiator)

After code is green, the harness docs are usually stale — they describe the old gates, miss new knobs, or cite removed symbols. Sync them:

- Update the repo's harness docs (`.claude/{rules,architecture,runbooks}` + interface pages, project `CLAUDE.md`) to match the new code/gates. Every claim carries a `file:line` or ADR citation that actually resolves. New gates/knobs (a type checker, coverage floor, cost cap, env var) get documented where operators look for them.
- **Deep-module / interface convention**: one source of truth per fact; the other tree *cites* it — never duplicate the same fact in two docs (they drift apart).
- Any contract a Phase-1 fix changed gets a new or amended **ADR**.
- Run the repo's deterministic **drift / doc-link guard** (e.g. `drift-scan.sh`, `check_doc_links.py`). If the repo has no such guard, install one and wire it into the verify path — mechanical `file:line`-integrity checks are the only thing that keeps docs honest at scale. (Semantic drift is a separate, human/skill pass — see `doc-management` AUDIT mode.)

Why this phase exists: a quality lift that leaves the docs lying is a regression in the dimension that matters most for the *next* engineer. This is the phase the bare review-loop engine does not have.

### Phase 4 — Verify + autonomous merge

1. Final faithful gate: full test suite + lint/type + drift-scan + verify-harness, all green locally (and CI-on-runner if available).
2. Single squash PR → main. PR body is the honest record: real weighted score (not a round number), the movers with evidence, and the **named residual risks**.
3. Merge per the project's policy. If CI cannot gate (billing/no-runner) and the project has an admin-merge precedent + standing authorization, admin-merge and say so plainly in the PR. Otherwise, stop at PR-created and hand the merge to the operator — do not bypass gates without authorization.
4. Tail cleanup: prune transient spec/plan docs per doc-lifecycle (durable content goes to ADRs/wiki first; verify no live links cite them — keep the ones an ADR still references). Remove leftover worktrees (`git worktree remove --force` + `prune`). Leave branch-ref deletion to the operator if a destructive-action guard blocks it — surface the branches, don't self-override the guard.

## Honest Definition of Done (lifecycle)

DoD is *honest*, not a forced number. The mode is "done" when:

1. Every **fixable** dimension reaches its target band, proven by its own gate.
2. Two consecutive adversarial rounds find zero new confirmed findings.
3. The harness docs match the code (drift guard green).
4. The work is merged (or PR-created + handed off if merge isn't authorized).

Report the **real weighted score reached**. If the realistic ceiling is below the aspirational target because some dimension is architecturally **frozen** (an accepted ADR limit) or externally **blocked** (CI can't run), say so up front and name it. Never inflate a dim to hit a round number; "95" or "92-94" is aspirational, and you state the gap and *why* it exists. A truthful 86 beats a fabricated 95 every time — and the conservative-eval rule requires it.

## Failure modes & stop guards (lifecycle)

- **Worker blocked** → PM provides context or escalates model tier; never silent.
- **Adversarial whack-a-mole** (no convergence, deny-list churn) → STOP, report "strategy change needed".
- **CI red after a ticket** → debug systematically before any further fix; don't pile on.
- **Eval track abstains** (Codex empty output / malformed) → retry once, then the Claude track stands and you surface the abstention. Don't pretend you had two tracks.
- **gh account drift** → re-check the active account before every push/PR/merge; it can silently revert.
- **Worktree branches off a stale base** → run workers on a worktree explicitly created off current HEAD, or serially on the main tree; a stale-base worktree silently drops work.

## Cross-references (lifecycle)

- ARL **codebase / multi-agent mode** (above) — the dimension fan-out engine. Cited, not duplicated.
- ARL **branch mode** (above) — the adversarial bug-hunt engine.
- `auto-pilot:quality-eval` — the 13-dim rubric, weights, hard-fail + anti-inflation rules (the rubric SoT this mode consumes).
- `auto-pilot:doc-management` (AUDIT mode) — semantic doc↔code drift (Phase 3 handles mechanical/known-gate drift; AUDIT handles unknown semantic drift).
- `auto-pilot:residue-audit` — dead-code/duplicate removal (a Phase-1 dimension tool).
- `superpowers:verification-before-completion` — evidence-before-assertions discipline behind the honest DoD.
