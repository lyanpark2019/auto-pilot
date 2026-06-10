---
type: architecture
topic: unified-coding-system
source_commit: 52776f7440fe2dd2bf472784717549be258b7c75
manual_edit: false
---

# auto-pilot architecture

## One-line

Opus 4.7 PM (main session) dispatches Sonnet 4.6 (1M ctx) workers in parallel, gates each diff through Codex + cold Claude dual adversarial review plus `review-gatekeeper` modes, runs phase verify checklists, commits atomically, advances phases until spec is complete. Full auto.

## Purpose (locked 2026-05-29)

auto-pilot autonomously drives **spec-based feature / refactor / bugfix work on an EXISTING codebase to merged**. Target = brownfield. Examples: "add OAuth to auth", "refactor payments", "fix these P1 bugs".

It is **NOT** a greenfield project generator and **NOT** a quality-eval loop.

Why brownfield: every friction guard presupposes existing code — composition-root breakage (`__init__.py` must already exist), SSL cascade, source-first debug (Naver private-bug class), scope-drift REJECT (`scope_files` constrains edits inside an existing tree), worktree + atomic merge to `$ROOT`. Born from 381-session `/insights` friction, all existing-project maintenance accidents.

## System Anatomy (round-2 §2.5)

### 4-Pillar purpose

| # | Pillar | Serves |
|---|--------|--------|
| ① | **자율 코딩 루프** — PM-worker-이중리뷰 | Contract-based dispatch, frozen-diff dual adversarial review, fixer convergence |
| ② | **문서 신선도** — doc-management flagship | REBUILD/AUDIT/MAINTAIN 3 modes; stale-doc assets absorbed or REMOVE |
| ③ | **지식 영속** — vault · retro · memory | Obsidian vault primary context, retro append-only, session handoff |
| ④ | **안전·집행** — hooks · contracts · gates | Enforcement-not-instruction; mechanical compensation for measured operator weaknesses (safety 55 / spec 62) |

Design principle: every asset must declare ≥1 pillar role. Assets without a declared role are REMOVE/merge candidates. Authoritative role table: `docs/asset-charter.md`.

### Coding-loop process (SoT: `agents/pm-orchestrator.md`)

```
PM (code-edit 0)
  → phase plan + tech-critic gate
  → contract 발행  [⛓ contract.schema.json · snapshot_shas SHA-pin · idempotency_token]
  → worker dispatch  (Sonnet 1M · worktree isolation)
  → diff + verify-log  [⛓ SHA-256 mandatory — missing = bounce]
  → review fan-out  [⛓ Codex read-only + cold Claude + review-gatekeeper modes · PM-frozen diff]
  → fixer commit  (re-review after commit — prevents timing artifacts)
  → merge  (human checkpoint, decision 14)
  → retro → memory  [⛓ vault gotchas + .claude/insights.md]
```

⛓ SHA evidence chain: every completion claim carries verifiable evidence — spec/CLAUDE.md SHA-pin fail-closed + tamper tests · verify-log SHA-256 · frozen diff (no tampering) · idempotency token for safe re-dispatch.

### Binding-contracts inventory

Full contract schemas and enforcement contracts: see README "Binding contracts inventory" section (this file cross-links; README is the pointer, `docs/asset-charter.md` holds role definitions).

| Contract | Form | Binds |
|----------|------|-------|
| worker | `schemas/contract.schema.json` v2 — target_repo · target_layer · hard_constraints · pattern_refs · snapshot_shas.project_context; `additionalProperties:false` fail-closed | worker scope · evidence · deadline |
| reviewer | read-only sandbox + frozen diff + structured APPROVE/REJECT (round-2: pre-mortem · liveness triage · 4 heuristics · round-budget gate); ticket roles are limited to live agents/modes (`codex-reviewer`, `claude-reviewer`, `review-gatekeeper`) plus worker/critic roles | Codex + cold Claude reviewers + gatekeeper modes |
| PM | `agents/pm-orchestrator.md` — reporting format · prohibited actions · code-edit 0 | PM main session |
| round-2 additions | `schemas/preflight.schema.json` (phase-key · TTL 900s · head_sha) · dispatch required fields · creation gate (asset_registry_check) · dispatch-manifest gate | all pre-dispatch stages |

### Dual improvement loops

**(a) Product loop** — `skills/adversarial-review-loop/` 3 modes:
- **branch**: review → fix → re-review; both sides must APPROVE
- **codebase**: 13-dim score → contract fan-out → re-score to target
- **multi-agent**: PM-Worker pool with activation gates

**(b) Self-improvement loop** — round-N SCORE → … → dual review (plugin targets itself):
retro appends evidence-cited gotchas to vault `intent/gotchas/` when a vault exists and to repo `.claude/insights.md` as the always-present memory surface. Converges via same stopping rule as product loop (same finding ≥2 rounds = escalation).

### Hermes ledger (discover-only self-improvement, shipped 2026-06-09/10)

Structured layer under loop (b): `scripts/learning_miner.py` + `scripts/_improvement.py` +
`schemas/improvement-ticket.schema.json`. Deterministic Python (no LLM), CLI shape mirrors
`scripts/risk_assess.py` (advisory exit 0, `--fail-on` exit 2, one-line JSON verdict).
Decisions locked by dual adversarial review (v1 draft was double-REJECTed):

- **Discover-only** — writes `state=candidate` tickets; acting on a `promotable` verdict stays
  human. Full FSM (candidate→…→promoted) declared in the schema for format stability, not enforced.
- **Durable ledger OUTSIDE the target repo** — `~/.claude/projects/<slug>/improvements/<fp>.json`.
  Brownfield driver must never pollute the driven repo's VCS; `--commit-to` is the explicit opt-in.
  Evidence is self-contained (snippet + run_id, never a dangling `path:line` into gitignored scratch).
- **Fingerprint** = sha256(source ‖ file_basename ‖ normalized_issue ‖ asset); normalization strips
  paths / line numbers / ISO dates / `phase-N`, keeps FULL issue text (8-token truncation collided).
- **Gate on `distinct_runs`, not raw occurrences** — reviewer-finding ≥2, doom-loop/insight/other ≥3
  → `promotable`; a worker re-tripping the same finding within one run cannot inflate the gate.
- **Inputs** (3 scanners): `critic-rejections-phase-*.jsonl`, `state.json` pivot_detector, and
  `insights.jsonl` — retro's structured sidecar where a `class` tag (not wording, not file) drives
  identity, because measured recurrence is semantic/class-level and a literal fingerprint fragments
  it. Honest corpus note: per-class volume measured WEAK (230 commits, ≤3 distinct days/class) —
  promotion machinery stays deferred until live runs accumulate real `distinct_runs`.
- **Wired via Stop hook** `hooks/learning-miner-stop.sh` (advisory, always exit 0, reentry-guarded).
  Once-per-session is sufficient: evidence dedups on (run_id, snippet), so re-fires cannot inflate.
  SubagentStop rejected (races the PM's jsonl write); PM-prose step rejected (enforce with code).
- **No run identity → non-persisting scan** (ADR `docs/adr/0001-empty-run-id-non-persisting.md`):
  empty/non-string `run_id` projects a verdict but persists nothing — a `""` phantom run otherwise
  shortcuts the `distinct_runs` gate by one run. No fallback id synthesis (re-imports the gaming).

### Memory 3-layer

| Layer | Location | Role |
|-------|----------|------|
| 1 | Obsidian vault `~/Documents/Knowledge/wiki/projects/<slug>/` | Primary context, code-only graph |
| 2 | `repo/.claude/insights.md` | Retro append-only ledger |
| 3 | Auto-memory session handoff | Cross-session state |

Context resolution 4-step: see `skills/auto-pilot/references/project-context-resolution.md` (do not re-enumerate here).

## Why this shape

Built directly from `/insights` friction analysis on 381 sessions:

| Friction (count) | Fix in auto-pilot |
|---|---|
| Wrong approach (83) | Source-first debug rule baked into PM contract |
| Buggy code (71) | Dual reviewer gate (Codex + cold Claude) blocks merge |
| Path typos (5+) | `preflight-path.sh` SessionStart hook |
| ruff --fix broke composition root (2+, 276 tests) | `pre-edit-composition-root.sh` blocks edits to *existing, populated* `__init__.py`/re-exports (new/empty inits pass) |
| SSL cascading outages | `pre-bash-guard.sh` blocks chained SSL config commands |
| Interactive TUI hung shell | `pre-bash-guard.sh` blocks `claude doctor` etc. |
| Verdict reversal (B4/B5 class) | Both reviewers must independently APPROVE |
| Whack-a-mole rounds | `pivot-check` exits when same finding repeats 3 rounds |

## Components (merged unified-coding-system layout, 2026-06)

Live asset counts (from `scripts/build_dashboard_data.collect_assets()`): 11 skills · 16 agents · 7 commands · 22 hooks · 12 codex-skills = 68 assets total.

```
auto-pilot/
├── .claude-plugin/plugin.json + marketplace.json
├── .mcp.json                          # notebooklm vault MCP
├── skills/  (11 dirs, all active SKILL.md)
│   ├── auto-pilot/                    # P①: entry skill / core loop
│   ├── adversarial-review-loop/       # P①④: branch/codebase/multi-agent + --lifecycle review
│   ├── doc-management/                # P②: REBUILD/MAINTAIN/AUDIT flagship
│   ├── setup-harness/                 # P④: harness bootstrap + scripts/references/templates/evals
│   ├── quality-eval/                  # P①: 13-dim rubric SoT
│   ├── residue-audit/                 # P②: semantic dead-code/duplicate audit
│   ├── sha-deploy-standard/           # P④: SHA-pinned deploy standard
│   ├── codex-orchestra/               # P①: Claude plans/reviews, Codex implements
│   ├── swarm/{init,start,status,stop,ticket,bench}/   # P①: parallel execution backend
│   ├── improve-codebase-architecture/, diagnosing/  # diagnostics (2 modes, merged 2026-06-07)
│   └── (deleted: codebase-perfection-loop, pm-quality-harness-loop → ARL --lifecycle,
│        swarm-bench → swarm bench, diagnosing-* pair → diagnosing; 2026-06-07)
├── agents/  (16 contracts)
│   ├── core: pm-orchestrator, worker, retro
│   ├── review (P①④): auto-pilot-{codex,claude}-reviewer (hardened pair —
│   │         legacy codex-adversarial/claude-reviewer deleted 2026-06-07),
│   │         tech-critic-lead, review-gatekeeper (tdd-enforcer + security-reviewer
│   │         merged 2026-06-07), specialist-pool (code-perfector retired 2026-06-07)
│   │         (harness-{planner,generator,evaluator} deleted 2026-06-07 — 1:1 duplicate of loop)
│   ├── swarm: swarm-{explorer,monitor,verifier}
│   └── vault (P③, 4 merged): vault-pm-orchestrator + vault-{edge,graph,knowledge,structure}-curator
│       (25 legacy workers removed round-2; goal-* removed → global ~/.claude/agents/)
├── hooks/  (22 scripts, P④; hooks/hooks.json is wiring SoT)
│   ├── preflight/edit/bash/reviewer guards + post-deploy/doc-sync/notebooklm/pm-final
│   ├── round-2/3 enforcement: branch/deletion/gh/ruff/dispatch/creation/context/artifact/subagent
│   ├── learning-miner-stop + worker-scope-gate (PreToolUse Edit/Write scope-allowlist)
│   └── guard-destructive.py + codex-conductor-guard.py + test_*.py (self-tests)
├── schemas/                           # PR1: contract/ticket/review/preflight JSON Schema 2020-12
├── scripts/                           # orchestrator.py, headless-loop.py, _*.py helpers, build_dashboard_data.py
├── prompts/ + vault/ + swarm/ + codex/  # PM/worker prompts; vault export; parallel backend; codex forks
├── deploy/ + dashboard/ + evals/
└── docs/
    ├── architecture.md (this file) + master-plan.md + perf-budget.md + 7-phase-template.md
    ├── asset-charter.md               # pillar→asset mapping SoT
    ├── history/                       # distilled changelogs
    └── specs/
```


## State

`.planning/auto-pilot/state.json` — SoT for loop state. Owned by `scripts/_state.py`. Writers hold `flock(LOCK_EX)` on `state.lock`; reads hold `LOCK_SH`. Writes use `_contract.atomic_write_text` (tempfile + fsync + rename, `F_FULLFSYNC` on Darwin) — never a partial file. Resume-safe: PM reads `current_phase` + `phases[last]`, continues from next contract.

Accumulates `cost_usd` + `tokens` across iters. Exceeds `--max-cost-usd` or `--max-tokens` → terminal `cost-cap`. `pgrep -x claude` GROWTH over the driver-start baseline (`args.pid_baseline`, captured in `headless-loop.main`) above `--max-concurrent-claude` → same exit (fork-bomb guard; ambient sessions on a busy host don't count).

Failure recovery is intentionally non-destructive: `headless-loop.py` snapshots pre-phase HEAD, but `status=failed` / timeout stashes dirty `$ROOT` state with a recoverable `auto-pilot-iter-N-{failed,timeout}` label instead of a destructive hard reset; per-worker worktree cleanup is the recovery unit.

## Contract layer (PR1)

Artifacts under `.planning/auto-pilot/contracts/iter-{N}/phase-{P}/contract-{K}/round-{R}/`: `contract.json` (schema-validated, read-only after write) · `PM-SIGNATURE` (MANIFEST+contract shas) · `context-bundle/` (spec.md, CLAUDE chain, MANIFEST.txt — read-only) · `tickets/<role>.json` · `review-input/frozen.diff` · `outputs/<role>/` (writable: status.json | review.json + exit-code.txt + done.marker) · `prior-rounds/round-N.jsonl` · `CANCELED` (PM kills in-flight subagents).

PM reads `done.marker` → `exit-code.txt` → `review.json | status.json` (PR1 invariant: never parses free-form output).

## Worktree lifecycle (PR2)

Each worker gets `git worktree add` under `.planning/auto-pilot/worktrees/auto-pilot/iter-N/phase-P/…`. PM mutates `$ROOT` only through `WorktreeManager.apply_to_main` (`main-apply.lock`) via `git format-patch | git am --3way --trailer auto-pilot-{iter,phase,contract,idempotency}`. Conflict → `git am --abort`, increment `merge_attempts`; 3 failures → `merge_pivot_needed`.

## Reviewer sandbox (PR3, 4 layers)

1. Agent frontmatter `tools:` whitelist — best-effort
2. `hooks/pre-reviewer-write.sh` PreToolUse (`AUTO_PILOT_SUBAGENT_ROLE`) — blocks Edit/Write/MultiEdit outside `$AUTO_PILOT_OUTPUT_DIR` + Bash mutations. **Real wall.**
3. PM `assert_reviewer_was_scoped` — `git status --porcelain` empty after every reviewer return. **Real wall.**
4. `codex exec --sandbox read-only` — model-layer deterrent (not OS-level).

Parallel reviewers use `scripts/_reviewer_wrapper.py` (isolated env per subprocess — prevents env-var signal race).

## Enforcement-guard behavior contracts (2026-06-10 campaign + F1 fixwave)

Six-dimension cold audit (Arch 84 · Docs 78 · Tests 76 · Agents 74 · Sec 71 · Enf 67) → 13 P1
closed across 5 clusters, then the F1 fixwave hardened the same guards via 4-round multi-model
adversarial review (different models found different bug classes). Durable contracts:

- **branch-lock**: `push` gates on the REFSPEC DST, never HEAD (post-merge `push origin feature`
  from main is legal); `commit` gates on HEAD. shlex tokenization (quoting evasions stripped);
  unanalyzable push (command-substitution / word-building / unbalanced quote) = fail-CLOSED deny;
  `--mirror/--all` denies if ANY local branch is protected; branch compare case-insensitive;
  path-qualified (`/usr/bin/git`) caught. `AUTO_PILOT_MAIN_OK=1` as hook env OR literal command
  prefix = operator intent (the hook inherits session env, so a tool-call prefix is the only way
  a per-command override can reach it).
- **gh-auth-preflight**: fires only when a segment's FIRST token basename-resolves to `gh`
  (env-prefix/wrapper aware); fail-toward-firing on `$(...)`/backtick next to a gh token
  (advisory — extra check harmless, missed wrong-account gh is not); 300s owner-keyed cache,
  purged on `gh auth switch`.
- **pre-reviewer-write**: fail-closed on unparseable payload / non-dict tool_input / non-string
  command; mutation deny-list fully boundary-anchored (substring FPs like "perform " fixed
  2026-06-10); `git -flag value` pairs skipped so `git -C <path> push` cannot bypass.
- **guard-destructive**: best-effort literal-pattern speed bump against accidents — NOT a sandbox;
  obfuscation (base64, var-indirection, `curl|sh`) is a documented architectural limit, not chased.
- **worker-scope-gate**: edit-time scope enforcement, inert until a dispatch path sets
  `AUTO_PILOT_SCOPE_FILES` (documented residual).
- **reviewer env** (`scripts/_reviewer_wrapper.py`): default-deny ALLOWLIST — F1 reversed the
  campaign's pattern-denylist decision after it leaked ~50% of common secret names; allow only
  what a `claude -p` subprocess needs (auth rides HOME, no credential var forwarded), secret-name
  regex kept as a second floor.
- **retro**: Tier-2 protected paths (e.g. this file) are report-to-PM, never direct agent edits
  (`hooks/pre-edit-human-only.sh`); retro's canonical output-target list is single-sourced.

## Evals harness (cut1 landed, cut2 advisory)

Two independent gates — never conflated:

- **Gate 1 — Task-success rate** (`scripts/evals/`): each case runs in a fresh `git clone --local`, executes `orchestrator.py init → headless-loop.py`, then `oracle.py` asserts the deliverable. Regression signal: Newcombe/Wilson two-proportion difference interval on the gated stable subset (cases with 0 baseline flips). Arming threshold: `A ≥ 50` gate attempts. Below that: advisory only.
- **Gate 2 — Harness health** (existing `dogfood_tier1/2`): kept separate — catches plumbing regressions that don't move the success rate.

Key constraints locked by adversarial review:
- Each case uses a **separate clone** (not a linked worktree) — inner `WorktreeManager` would create branch/rebase-apply namespace collisions across a shared gitdir.
- `_budget.py check_caps` measures `claude` pid growth over the driver-start baseline (Step-0 live fix 2026-06-10); evals still pass `--max-concurrent-claude UNCAPPED` as belt-and-suspenders.
- `run_case` returns `CaseAttempt(oracle: OracleResult, run: RunResult)` so per-case cost is surfaced for the total-cost ceiling.
- Deterministic oracle only (no LLM-judge). `error` outcome counts as non-pass.

## Toolkit consolidation (v0.4.0, decisions locked 2026-05-29)

Authored skills/hooks bundled into this plugin as the canonical home. Key decisions from dual adversarial review:
- `setup-harness` is a nested plugin (carries its own agents/commands); it does NOT bundle as a skill subtree — that would silently drop 11 components.
- Only the two decision-guard hooks bundle: `guard-destructive.py` + `codex-conductor-guard.py`. Cleanup hooks excluded (destructive/personal-hardcoded).
- Plugin must validate (`claude plugin validate .`) and be installed before bundling has any observable effect; the installed plugin loads from a version-bucketed cache snapshot.
- Path fixups in skill bodies use `$SKILL_DIR` self-location or relative paths — NOT `${CLAUDE_PLUGIN_ROOT}` (that var only expands in `hooks.json` command strings and the manifest).
- Plugin skills are namespaced `auto-pilot:<skill>`. Cross-references within the plugin must be namespace-aware.

## Why a plugin (not skill alone)

- Skills can't bundle hooks. Friction guards are hook-only.
- Plugins are atomic install/uninstall, version-tagged, marketplace-shippable.
- Per-repo `${CLAUDE_PLUGIN_ROOT}` makes the loop relocatable.

## Reuse across projects

Plugin is global. Drop it into any repo that has:
- `docs/specs/*.md` or `SPEC.md` with `## Phase N` headers
- `CLAUDE.md` with verify commands
- A git remote (for atomic commits)

Then: `/auto-pilot start`.

## Non-goals

- This is NOT a quality-eval / scoring loop — for that, use `adversarial-review-loop` skill (codebase mode).
- This is NOT a one-shot review — for that, use `/code-review` or `/codex-orchestra`.
- This is NOT a babysitter for already-merged PRs — for that, use `gh pr` + manual checks.

`auto-pilot` is specifically: "given a spec with phases, drive it to done autonomously."
