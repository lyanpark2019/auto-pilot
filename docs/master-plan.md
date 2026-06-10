---
type: plan
topic: auto-pilot-master-plan
source_commit: 52776f7440fe2dd2bf472784717549be258b7c75
manual_edit: false
---

# auto-pilot — master plan & status

> **Single context entry point.** Read this first to grasp purpose, what's done, what's next.
> Loop design detail: [`architecture.md`](architecture.md). Per-change design specs: [`specs/`](specs/).

---

## 1. Purpose (locked 2026-05-29)

auto-pilot is an autonomous development loop that drives **spec-based feature / refactor / bugfix work on an EXISTING codebase to merged**, by **integrating the existing Claude Code skill ecosystem** into each loop stage.

- **Target: brownfield only.** Existing repo with code, tests, conventions. Examples: "add OAuth to auth", "refactor payments", "fix these P1 bugs".
- **NOT** a greenfield project generator. **NOT** a standalone quality-eval scorer.
- **The novelty:** the PM→Worker→Review→Verify→Commit backbone does not reimplement each stage — it **delegates to a best-in-class skill** where one exists. auto-pilot is the orchestration glue + the safety guards (hooks, sandbox, contract layer) that let those skills run unattended.

Why brownfield: every friction guard presupposes existing code (composition-root breakage, scope-drift REJECT, source-first debug, worktree + atomic merge to `$ROOT`). Born from 381-session `/insights` friction — all existing-project maintenance accidents.

> **Scope note (2026-05-29):** a brief mid-session idea to make auto-pilot a multi-mode "build/review/perfect" platform was **dropped**. The skill/hook → plugin packaging & management concern moved to a **separate new project, `plugin-forge`** (a plugin generator that composes managed plugins from the user's existing hand-made skills/hooks). auto-pilot stays build-only and is simply one of the plugins `plugin-forge` will manage.

## 2. Skill integration map

Each loop stage routes to a skill/agent. This is the "system that integrates various skills" view.

| Loop stage | Integrated skill / agent | Status |
|---|---|---|
| Context / code map | **graphify** (`graphify-out/`) | 🔜 deferred → after live loop (see §5) |
| Pre-dispatch scope gate | `tech-critic-lead` (internal agent) | ✅ built |
| Implementation | `worker` subagent (Sonnet 4.6, 1M) | ✅ built |
| Adversarial review | `codex` + cold `claude` reviewers | ✅ built |
| TDD / security gates | `review-gatekeeper` (`tdd-gate` + `security` modes) | ✅ built |
| Verify / scoring | project verify cmds (+ `adversarial-review-loop` codebase mode, optional) | ✅ / 🔜 |
| Doc sync | `doc-management` (MAINTAIN/AUDIT modes) | 🔜 planned |
| Progress / decisions log | `PROGRESS.md` + `decisions.md` writer | 🔜 (Q2) |

## 3. What it is (structure)

A **plugin** (container) bundling: skills, commands, agents, hooks, schemas, Python helpers. Why a plugin and not a lone skill: **hooks cannot ship inside a skill**, and the friction guards are hook-only. Layout: see project `CLAUDE.md`.

Runtime roles (easy to confuse):
- **PM** = the main Opus session itself, reading `agents/pm-orchestrator.md` as its contract. **Never dispatched as a subagent.**
- **Workers** = dispatched via the `Agent` tool; **reviewers** = hardened reviewer agents, with `scripts/_reviewer_wrapper.py` used for parallel `claude -p` subprocess dispatch when env isolation is required. PM contract is the SoT.

## 4. Progress

### Done — PR1–PR5, all merged
- **PR1** contract layer — JSON-Schema-validated, PM-signed, snapshot SHAs
- **PR2** worktree lifecycle — create / apply / reap + merge-conflict state machine
- **PR3** reviewer sandbox — 4-layer; the PreToolUse hook + post-check are the real walls
- **PR4** state lock + crash-safe resume + cost cap + dogfood gates
- **PR5** verify-cleanup — regex fix, `_budget` extract, dedupe, dead-code prune
- **Reviewer role alignment** — dispatch tickets now accept only live review roles (`codex-reviewer`, `claude-reviewer`, `review-gatekeeper`) plus worker/critic roles; retired `tdd-enforcer` / `security-reviewer` roles are rejected by schema and regression tests.
- **Failure recovery alignment** — headless failures use recoverable `stash_if_dirty` labels instead of destructive root resets; command/agent/README docs use that behavior as the current contract.
- Test suite, mypy, and ruff were clean at merge time; do not duplicate collected test counts here (pytest output is the SoT).

### Not yet proven (honest gaps)
- ~~Live e2e loop NEVER run~~ **PROVEN 2026-06-10** (Step 0 below): one full live cycle green — but only 1 phase / 1 contract / trivial 4-line diff / round-1 dual APPROVE. Still unproven: reviewer REJECT → fix round, multi-contract parallel dispatch, merge-conflict path, multi-phase advance.
- **Loop logic is PM markdown**, not deterministic code → no test covers the dispatch/gate flow.
- **Context ingestion bundles only spec + CLAUDE.md** (greenfield-shaped) → brownfield PM/workers are blind to existing code. This is the Q1 fix below.

## 5. Current work (RESEQUENCED after adversarial review 2026-05-29)

Dual adversarial review (Codex + cold Claude) found the original "graphify first" plan unsound: P0×5, P1×3, P2×3. Two contradictions are fatal and must be resolved before any code — see §6. The corrected sequence proves the core loop live **before** layering graphify.

### Step 0 — prove the bare loop live — ✅ DONE 2026-06-10
1. **Skill-fire smoke:** prose trigger ("Run the auto-pilot skill") FIRES the skill in `claude -p`; explicit `/auto-pilot <args>` as the `-p` prompt does NOT route through the Skill tool (answered ad-hoc). headless-loop's prose iteration prompt is the validated mechanism.
2. **Bare e2e:** spec `docs/specs/2026-06-10-step0-brownfield-smoke.md` ran live end-to-end → commit `f4a2f59` on origin/main, CI green. Full chain exercised with real subagents: preflight → contract scaffold/sign → tech-critic → worktree → Sonnet worker → frozen diff → risk_assess → dual reviewers (codex 0 findings, claude 1 P2) → verify trio → `apply_to_main` + trailers → push → reap. ~10 min, 1 round.
   Breaks captured (fixed same-day): pid-cap counted host-global claude processes (→ baseline-delta in `_budget.check_caps`); `.auto-pilot-worktree` sentinel untracked → false scope-trip (→ worktree-local `info/exclude`). Open P2/P3: cap-abort poisons state.json terminally; `phases[].approved` never bumps; driver prompt says 0-indexed phase; `pm-final-report-*.md` unrotated (~117); specialist-pool maps tests-only diffs to unported reviewer.

### Step 1 — deterministic discovery seam + schema — ✅ DONE 2026-06-10
- `scripts/_discovery.py` + `orchestrator.py discover --record|--check` landed. `--record` writes `graphify-provenance.json` (build_commit + graphify_version + recorded_at) under `.planning/auto-pilot/` AFTER the PM ran graphify; Python never snapshots the graph itself. `--check` is a pure-git diff-relevance verdict (exit 0 fresh / 1 stale): stale on never-recorded / corrupt / version-changed / unknown-build-commit / scope-intersects / changed-no-scope (conservative when no scope given); fresh on same-commit / no-scope-overlap. Trailing-slash scope entries match as dir prefixes.
- `graphify-out/` already gitignored (predates Step 1) — clean-tree preflight unaffected.
- Schema v2 landed earlier in round-2 W2 unified migration (project_context seat + dispatch required fields).

### Step 2 — copy graphify context INTO the bundle — ✅ DONE 2026-06-10 (wiring; live-run pending)
- Mechanics were already in place from the round-2 W2 migration: `_contract.snapshot_context(project_context_path=…)` copies the report bytes as `context-bundle/project-context.md`, SHA-pins them into `snapshot_shas.project_context` + MANIFEST, and `verify_snapshots` fail-closes on declared-but-missing/tampered bytes ("ran context-blind" log when absent).
- This step added the missing seam: `_discovery.resolve_report(repo_root, state_dir, graphify_version, scope_files)` → `(path | None, Freshness)` — returns `graphify-out/GRAPH_REPORT.md` only when it exists AND provenance is fresh (diff-relevance + version match). PM contract (`agents/pm-orchestrator.md` dispatch step 0) wires it: None → regen graphify + `discover --record` + resolve again; still None → context-blind, never blocks dispatch. Dispatch prompt template now lists `project-context.md`.
- ~~NOT yet proven live~~ **PROVEN 2026-06-10 (2nd live run)**: iter-1 bundle carried `project-context.md` with `snapshot_shas.project_context` = `c84fd00b…` (pinned in that run's contract.json); phase 1 merged `75b995d` (in-repo anchor) after dual APPROVE; phase-2 worker commit recovered via cherry-pick (`37e7441`) after run stop.
- Live run 2 also surfaced **F-6 (P1)**: headless PM dispatched reviewers in background then exited — one-shot `-p` session has no wake-up, so iters 2-3 burned re-validating the same phase; the run advanced only because orphaned reviewers happened to finish and iter-3 collected them (resume logic sound, progress was luck). Fixed prompt-side: `prompts/headless.md` + `iteration.md` mandate synchronous dispatch / no in-flight exit, pinned by prompt-regression fixtures 07/11; `skills/auto-pilot/SKILL.md` headless block cites the rule. **Residual (P2, deliberate)**: no deterministic guard yet — a hook blocking background dispatch under `HARNESS_HEADLESS=1` needs pid-to-session attribution design ("enforce with code" follow-up).

### Step 3 — relevance digest (OPTIONAL, measured)
- Build a PM-authored, scope-sliced `project-map.md` digest **only if** workers measurably degrade on the full report. Measure before optimizing. Split global-map (pre-PLAN) from per-contract slice (post-tech-critic) to avoid the circular timing (slice needs `scope_files`, which PLAN produces).

### P1 — Q2 progress / decisions docs (parallel-safe, any time)
- PM writes `.planning/auto-pilot/PROGRESS.md` + `decisions.md` at every phase-end. Optionally wire `doc-management` (AUDIT mode) after merges.

## 6. Resolved decisions + fatal contradictions

**Fatal (resolved by resequence):**
- **SHA-pin vs nondeterministic graphify** — pin the *copied report/digest bytes* (integrity = "worker reads what PM signed"), NOT the graph (graphify's LLM semantic layer is non-reproducible). Record the graph only by provenance (`base_sha` + version).
- **graphify-out/ unreachable from worktrees** — copy needed context into `context-bundle/`; gitignore the raw output; no drill-down.
- **Sequencing** — prove the loop live (Step 0) before adding graphify (Steps 1-3).

**Resolved:**
- Q3 bundle shape → full `GRAPH_REPORT.md` copy first; relevance-digest deferred + measured (Step 2 → 3).
- Freshness → diff-relevance / `--update`, not sha-equality.
- Schema → `project_context` optional + fail-closed verify + schema_version 2.

**Still open:**
- **Q4 verify integration** — wire `adversarial-review-loop` (codebase mode) as an optional verify-stage scorer, or keep verify = project test/lint/typecheck only? (NOT `quality-eval` — superseded, see §8.)
- Whether to keep review as internal codex+claude agents or delegate to the `adversarial-review-loop` skill branch mode (which already does Codex+Claude independent review → cross-verify → approve). Skill-integration consistency vs proven internal path.

## 8. Skill-ecosystem currency (audit 2026-05-29)

Integration targets must point at the canonical, current skill — verified on disk:

| Skill | Status | Plan action |
|---|---|---|
| `adversarial-review-loop` (May 25) | ✅ canonical for review + codebase quality | use for Q4 + review-delegation option |
| `quality-eval` (May 18) | ⚠️ superseded by adversarial-review-loop | do NOT integrate; was stale ref in earlier draft |
| `quality-loop` | no standalone skill (command delegates) | n/a |
| `codebase-perfection-loop` (May 16) | ⚠️ older, overlaps adversarial-review-loop multi-agent | do NOT integrate |
| `doc-drift-audit` (May 29) | ⚠️ absorbed into `doc-management` (AUDIT mode, 2026-06-06) | use `doc-management` for post-merge doc sync (P1) |
| `graphify` v0.8.14 | ✅ current, but **duplicate install**: canonical `~/.claude/skills/graphify` + orphan `~/.agents/skills/graphify` (older) | clean the orphan to avoid future drift; graphify provides `GRAPH_REPORT.md` + `--update` but NO `.build-commit` — auto-pilot owns that marker |

Also: the headless loop docstring now names the prose trigger form used by `prompts/iteration.md` ("Run the auto-pilot skill", no explicit slash). Step-0 skill-fire smoke still must record whether that trigger works in live `claude -p`.

## 7. Cost model
- **Interactive subscription (this user):** token $ is irrelevant — global rule is *speed > token cost*. graphify regen is gated on latency + redundancy only, never $.
- **API-billed headless (other users):** `headless-loop.py --max-cost-usd` is a real $ guard. **graphify token spend must count against this cap** — and if `GEMINI_API_KEY`/`GOOGLE_API_KEY` is unset, graphify falls back to dispatching Claude subagents from the host session (nested dispatch under `--dangerously-skip-permissions`). Headless path should set a Gemini key so extraction doesn't recurse, and the cap must account for graphify's burn.
