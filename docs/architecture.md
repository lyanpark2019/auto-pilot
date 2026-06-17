---
type: architecture
topic: unified-coding-system
source_commit: 52776f7440fe2dd2bf472784717549be258b7c75
manual_edit: true
---

# auto-pilot architecture

## One-line

The main-session PM dispatches Sonnet 4.6 (1M ctx) workers in parallel, gates each diff through Codex + cold Claude dual adversarial review plus `review-gatekeeper` modes, runs phase verify checklists, commits atomically, advances phases until spec is complete. Full auto.

> Single index of every policy the loop enforces (budget / routing / risk / sandbox / scope / escalation / learnings gate / state): `docs/governance.md`.

## Purpose

> Two-level identity (SoT: `CONTEXT.md`; purpose narrative: `docs/master-plan.md`).
> The **plugin** is a brownfield toolkit built on an Obsidian **vault** substrate;
> the **loop** below is its single-purpose flagship.

The auto-pilot **loop** autonomously drives **spec-based feature / refactor / bugfix work on an EXISTING codebase to merged**. Target = brownfield. Examples: "add OAuth to auth", "refactor payments", "fix these P1 bugs".

The loop is single-mode — **NOT** a greenfield generator and **NOT** a quality-eval loop. The plugin around it bundles other standalone tools (vault automation, doc-management, swarm, harness).

Why brownfield: every friction guard presupposes existing code — composition-root breakage (`__init__.py` must already exist), SSL cascade, source-first debug (Naver private-bug class), scope-drift REJECT (`scope_files` constrains edits inside an existing tree), worktree + atomic merge to `$ROOT`. Born from 381-session `/insights` friction, all existing-project maintenance accidents.

**Vault-as-substrate reframe (2026-06-14):** the four pillars below sit on the vault as a knowledge substrate, not beside it — the vault is the shared memory the loop reads from and writes to. A continuous autoresearch loop enriches it with verified external knowledge; mistakes and the installed project's conversation history flow back in; the relevant slice is injected at dispatch. First increment = the **closed learning loop**: `docs/specs/2026-06-14-closed-learning-loop.md`. Store split (Ledger = SoT, vault = mirror): `docs/adr/0002-ledger-sot-vault-mirror.md`.

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
| reviewer | read-only sandbox + frozen diff + structured APPROVE/REJECT (+wrapper-emitted ABSTAIN) (round-2: pre-mortem · liveness triage · 4 heuristics · round-budget gate); ticket roles are limited to live agents/modes (`codex-reviewer`, `claude-reviewer`, `review-gatekeeper`) plus worker/critic roles | Codex + cold Claude reviewers + gatekeeper modes |
| PM | `agents/pm-orchestrator.md` — reporting format · prohibited actions · code-edit 0 | PM main session |
| round-2 additions | `schemas/preflight.schema.json` (phase-key · TTL 900s · head_sha) · dispatch required fields · creation gate (asset_registry_check) · dispatch-manifest gate | all pre-dispatch stages |

### Dual improvement loops

**(a) Product loop** — `skills/adversarial-review-loop/` 3 modes:
- **branch**: review → fix → re-review; both sides must APPROVE
- **codebase**: 13-dim score → contract fan-out → re-score to target
- **multi-agent**: PM-Worker pool with activation gates

**(b) Self-improvement loop** — round-N SCORE → … → dual review (plugin targets itself):
retro appends evidence-cited gotchas to vault `intent/gotchas/` when a vault exists and to repo `.claude/insights.md` as the always-present memory surface. Converges via same stopping rule as product loop (same finding ≥2 rounds = escalation).

### Improvement-ticket ledger (discover-only self-improvement, shipped 2026-06-09/10)

Structured layer under loop (b): `scripts/learning_miner.py` + `scripts/_improvement.py` +
`schemas/improvement-ticket.schema.json`. Deterministic Python (no LLM), CLI shape mirrors
`scripts/risk_assess.py` (advisory exit 0, `--fail-on` exit 2, one-line JSON verdict).
Decisions locked by dual adversarial review (v1 draft was double-REJECTed):

- **Discover-only** — writes `state=candidate` tickets; acting on a `promotable` verdict stays
  human. Full FSM (candidate→…→promoted) declared in the schema; Phase-1 (2026-06-13) made the
  later transitions code-enforced — see the Phase-1 bullet below (`_promotion.py:TRANSITIONS`).
- **Durable ledger OUTSIDE the target repo** — `~/.claude/projects/<slug>/improvements/<fp>.json`.
  Brownfield driver must never pollute the driven repo's VCS; `--commit-to` is the explicit opt-in.
  Evidence is self-contained (snippet + run_id, never a dangling `path:line` into gitignored scratch).
- **Fingerprint** = sha256(source ‖ file_basename ‖ normalized_issue ‖ asset); normalization strips
  paths / line numbers / ISO dates / `phase-N`, keeps FULL issue text (8-token truncation collided).
- **Gate on `distinct_runs`, not raw occurrences** — reviewer-finding ≥2, doom-loop/insight/other ≥3
  → `promotable`; a worker re-tripping the same finding within one run cannot inflate the gate.
  Captured reviewer-finding lines carry the `run_id` of the run that PRODUCED the review (read from
  the contract's `PM-SIGNATURE`), so a later session re-sweeping persisted `review.json` files stamps
  the SAME id and cannot inflate `distinct_runs` (an unsigned contract dir falls back to the
  scan-time run_id — unreachable in normal dispatch, where ticket prep verifies the signature).
  `scan_reviewer_findings` credits that per-line id;
  a legacy line with no `run_id` collapses to one synthetic sentinel (`__legacy_no_run_id__`), never
  the live state run_id, so re-mining it after the next `init` cannot inflate either. Genuine
  cross-run recurrence is required (D1 2026-06-16; provenance + sentinel hardening D2 2026-06-17).
- **R1 — reviewer-finding keys on a controlled-vocab `class`, not free prose (2026-06-17)** — R1
  measured that `normalize_issue` keeps wording, so one defect phrased N ways fingerprints N times →
  a 100%-recurring bug reviewed 6× yielded 0 promotable tickets. Fix: reviewers emit an optional
  `class` from the `schemas/review.schema.json` `findings[].class` enum; `_capture_reviews` carries it
  into the JSONL; `scan_reviewer_findings` seeds the fingerprint on `class` (basename kept) when it is
  in `learning_miner.REVIEWER_FINDING_CLASSES`, else falls back to `issue`. Same defect, different
  wording, now collapses to ONE ticket so `distinct_runs` accumulates. Mirrors the long-standing
  `insight` class-tag pattern. The vocab is enforced in the miner allow-list, not the schema —
  `review.schema.json` keeps `class` a permissive `string|null` so a reviewer typo or `null` can
  never fail review.json validation (it would otherwise sink the whole review through the evidence
  gate's `read_review`); an out-of-vocab class simply degrades to issue-keying. Honest limits:
  (1) the long tail with no fitting class still keys on prose; (2) two genuinely-distinct defects in
  one file sharing a class across two runs over-collapse into one promotable ticket — bounded by the
  human `user_approved` promotion gate, not eliminated; (3) efficacy across the CROSS-MODEL pair
  (codex vs claude independently picking the SAME token for one defect) is the real R1 unknown and is
  UNPROVEN — class-keying is a hypothesis the first live run measures, not a closed result.
- **Inputs** (3 scanners): `critic-rejections-phase-*.jsonl`, `state.json` pivot_detector, and
  `insights.jsonl` — retro's structured sidecar where a class tag (not wording, not file) drives
  identity, because measured recurrence is semantic/class-level and a literal fingerprint fragments
  it. Honest corpus note: per-class volume measured WEAK (230 commits, ≤3 distinct days/class).
  The first scanner is fed by a deterministic CODE producer — `scripts/_capture_reviews.py`
  (`orchestrator.py capture-reviews` / `capture-all-phases`) converts dual-reviewer REJECT
  `review.json` findings (P0/P1) into JSONL lines. The Stop hook (below) calls `capture-all-phases`
  before mining, so capture fires automatically at session end across every phase — including
  pivot-aborted phases that never reach a clean phase-end — with no PM prose (D2 2026-06-17).
- **Phase-1 promotion CLI shipped 2026-06-13** (`scripts/_promotion.py:138`, three orchestrator
  subcommands `improvements-list/gate/set-state`). FSM is now enforced on every transition: the
  state machine in `_promotion.py:TRANSITIONS` rejects illegal jumps at write time. `promoted`
  requires all three `promotion_gate` fields (`tests_pass`, `ci_pass`, `user_approved`) to be
  `True` before the transition is accepted. Asset authoring and approval stay human — `user_approved`
  is only set on an explicit user directive; the CLI records and validates, never auto-decides.
- **Phase-2 vault mirror shipped 2026-06-14** (`scripts/_mirror_learnings.py`, `orchestrator.py
  improvements-mirror`): derived, idempotent one-way sync — each gate-passed ticket becomes a
  `gotchas/gotcha-<fp>.md` page in the project vault. Ledger is SoT (ADR 0002); vault is
  human-browsable mirror only. Re-runs are byte-stable; pages for tickets no longer promotable
  are pruned; hand-authored pages (no generator sentinel) are never touched. Shared predicate
  `_learnings.is_gate_passed` (public since Phase-2) defines "gate-passed" for both injection
  (Phase-3) and mirror (Phase-2).
- **Wired via Stop hook** `hooks/learning-miner-stop.sh` (advisory, always exit 0, reentry-guarded):
  it sweeps capture (`capture-all-phases`) THEN mines, so the producer→consumer chain runs at session
  end with no PM prose. Once-per-session is sufficient: evidence dedups on (run_id, snippet), so
  re-fires cannot inflate. SubagentStop rejected (races the PM's jsonl write); PM-prose step rejected
  (enforce with code).
- **No run identity → non-persisting scan** (ADR `docs/adr/0001-empty-run-id-non-persisting.md`):
  empty/non-string `run_id` projects a verdict but persists nothing — a `""` phantom run otherwise
  shortcuts the `distinct_runs` gate by one run. No fallback id synthesis (re-imports the gaming).
- **Increment-2 Phase-1 — enrichment gate shipped 2026-06-14** (`scripts/_enrich_gate.py` +
  `schemas/enrichment-evidence.schema.json`): deterministic gate that must pass before any
  external fact enters the vault. Rules: `snippet` non-empty + `source_url` present +
  `retrieved_date` valid ISO + `sha256 == sha256(snippet.utf-8)` (tamper-evident); official
  tier admits on evidence-complete alone; community tier additionally requires ≥2 independent
  corroborations (distinct hosts, each sha-valid) OR `repro_passed=True`. `llm_judge` is
  recorded in the verdict output but NEVER overrides ADMIT/REJECT ("enforce with code, not
  prompts"). ADR: `docs/adr/0003-gated-ondemand-enrich-two-tier-escalation.md`.
- **Increment-2 Phase-2a — enrichment gate-and-persist shipped 2026-06-14**
  (`scripts/_enrich_persist.py`, `orchestrator.py enrich` subcommand): deterministic
  persistence layer. Takes candidate enrichment-evidence JSONs (from a file/dir), runs each
  through the Phase-1 gate, and ADMITted candidates are persisted as vault
  ``enrichment/enrich-<sha256>.md`` pages. Enrichment is ADDITIVE/UPSERT — pages are
  accumulated verified knowledge keyed by content sha, never pruned.
- **Increment-2 Phase-2b — live MCP-fetch enrichment producer shipped 2026-06-14**
  (`scripts/_enrich_fetch.py` + `agents/enrichment-fetcher.md`): injectable Fetcher
  Protocol seam (MCP boundary) with `shape_hit` (sha-computing, pure) and
  `fetch_and_persist` (Fetcher → shaped candidates → existing `persist()`). The agent
  owns live MCP I/O (context7 → web → community); the Python module owns deterministic
  shaping and is fully testable with FakeFetcher. Agent never writes vault pages directly.
- **Increment-2 Phase-3 — escalation-record schema + producer shipped 2026-06-14**
  (`schemas/escalation-record.schema.json` + `scripts/_escalation.py`, 9 schemas total):
  typed escalation record `{problem_class, tried, evidence, suggested_enrich_query}` —
  the tier-1→tier-2 boundary marker (inc 3) and the enrich trigger.  A tier-1 gate that
  cannot resolve a case emits one; `suggested_enrich_query` feeds Phase-2 via
  `drive_enrich`.  CLI: `orchestrator.py escalation-record|escalation-list|escalation-enrich`.
  Inc 3 design SoT: `docs/specs/2026-06-15-two-tier-escalation-increment3.md`.
- **Phase-4 measurement (G1 input) — 2026-06-14** (`scripts/measure_learnings_injection.py`,
  `orchestrator.py measure-injection`): on the current real ledger all 7 gate-passed tickets are
  file-less `insight` tickets (`scope_blind=7`, `scope_addressable_pct=0.0`); the one `doom-loop`
  ticket sits at `candidate` below its promotion threshold and is excluded from gate-passed.
  Scope-match injection serves ONLY file-anchored (reviewer-finding) tickets; there are 0 such
  promotable tickets in the ledger yet, so the file-anchored path's in-the-wild recall is
  **unmeasured**. The before/after delta is **null because nothing is injection-eligible** —
  every contract runs learnings-blind on this ledger — not because injection is broken
  (`test_select_tickets_matches_promotable_by_scope` proves the file-anchored path works).
  **G1 decision input:** deterministic scope-match under-serves an insight-dominated ledger; a
  non-file relevance signal (source/asset-type or semantic) would be needed for file-less tickets —
  but per "measure before optimizing", DEFER G1 until an external-repo run produces file-anchored
  reviewer-finding tickets to measure the file-anchored recall in the wild.
- **D1 — code-side capture + organic recurrence proof shipped 2026-06-16** (`scripts/_capture_reviews.py`,
  PR #97): the deterministic producer above plus the run-scoped `distinct_runs` fix make the
  reviewer-finding path injectable from real reviewer output, not just a synthetic seed.
  `tests/test_capture_reviews_e2e.py` drives capture→mine→resolve→measure on `review.json` fixtures
  only (no `_improvement.bump_or_create` seeding): a genuine 2-run recurrence flips
  `scope_addressable_pct` 0.0→100.0, and `test_stale_finding_not_recredited_to_new_run` guards the
  anti-inflation semantics. Honest limits: fixtures hold issue wording constant — `normalize_issue`
  strips path/line/date/phase noise but NOT wording, so real-reviewer phrasing variance across genuine
  runs may prevent `distinct_runs` accumulation (untested in the wild); legacy prose lines without
  `run_id` remain re-mine-inflatable; L2 (does injection improve outcomes) stays deferred per
  `evals/cases/learnings-ab`.
- **D2 — both-sides invocation enforcement + provenance run_id shipped 2026-06-17** (PR #99 capture
  side + inject-side runtime gate): neither learning-loop side depends on PM prose any more. CAPTURE
  fires automatically at the Stop hook (`learning-miner-stop.sh` runs `capture-all-phases` before
  mining); each captured line's `run_id` comes from the contract's `PM-SIGNATURE` (provenance), so a
  later session re-sweeping persisted `review.json` cannot inflate `distinct_runs`, and legacy
  no-`run_id` lines collapse to one synthetic sentinel — superseding D1's "legacy lines remain
  re-mine-inflatable" limit. INJECT is runtime-gated: `_learnings.resolve_learnings` ALWAYS writes
  `context-bundle/learnings.md` (a marker on the blind path), and `hooks/dispatch-contract-gate.sh`
  DENIES a worker dispatch whose bundle lacks it — skipping resolve blocks the loop. Residual: the
  inject gate fires only on marked dispatches (the gate's documented no-marker bypass is unchanged);
  R1 phrasing variance + L2 outcome stay deferred.

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

Live asset counts (from `scripts/build_dashboard_data.collect_assets()`): 11 skills · 18 agents · 7 commands · 28 hooks · 12 codex-skills = 76 assets total.

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
├── hooks/  (27 wired, P④; hooks/hooks.json is wiring SoT; + _stdin_contract.py helper = 28 files)
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
    ├── onboarding/README.md           # AI/developer start path: architecture map, task routing, graphify commands (shipped 2026-06-07); What/Why discipline: graphify is the What (current code), architecture/ADR docs are the Why (rationale)
    ├── history/                       # distilled changelogs
    └── specs/
```

`skills/auto-pilot/tests/skill-snippets.bats` pins load-bearing Step 7 (reviewer registry check) and Step 8 (codex sandbox probe) fenced snippets in `SKILL.md` (PR#33, 2026-06-12); wired into CI alongside the ARL and setup-harness bats suites.


## State

`.planning/auto-pilot/state.json` — SoT for loop state. Owned by `scripts/_state.py`. Writers hold `flock(LOCK_EX)` on `state.lock`; reads hold `LOCK_SH`. Writes use `_contract.atomic_write_text` (tempfile + fsync + rename, `F_FULLFSYNC` on Darwin) — never a partial file. Resume-safe: PM reads `current_phase` + `phases[last]`, continues from next contract.

Accumulates `cost_usd` + `tokens` across iters. Exceeds `--max-cost-usd` or `--max-tokens` → terminal `cost-cap`. `pgrep -x claude` GROWTH over the driver-start baseline (`args.pid_baseline`, captured in `headless-loop.main`) above `--max-concurrent-claude` → same exit (fork-bomb guard; ambient sessions on a busy host don't count). `cost-cap` is recoverable: `python3 scripts/orchestrator.py resume` clears the status to `running` (preserving accumulated `cost_usd`/`tokens`), then re-run `headless-loop.py` with raised `--max-cost-usd`/`--max-tokens`.

Failure recovery is intentionally non-destructive: `headless-loop.py` snapshots pre-phase HEAD, but `status=failed` / timeout stashes dirty `$ROOT` state with a recoverable `auto-pilot-iter-N-{failed,timeout}` label instead of a destructive hard reset; per-worker worktree cleanup is the recovery unit.

## Contract layer (PR1)

Artifacts under `.planning/auto-pilot/contracts/iter-{N}/phase-{P}/contract-{K}/round-{R}/`: `contract.json` (schema-validated, read-only after write) · `PM-SIGNATURE` (MANIFEST+contract shas) · `context-bundle/` (spec.md, CLAUDE chain, MANIFEST.txt — read-only) · `tickets/<role>.json` · `review-input/frozen.diff` · `outputs/<role>/` (writable: status.json | review.json + exit-code.txt + done.marker) · `prior-rounds/round-N.jsonl` · `CANCELED` (PM kills in-flight subagents).

PM reads `done.marker` → `exit-code.txt` → `review.json | status.json` (PR1 invariant: never parses free-form output).

### Discovery seam (Step 1, 2026-06-10)

`scripts/_discovery.py` + `orchestrator.py discover --record|--check`. The PM runs graphify itself, then `--record` persists provenance only (`graphify-provenance.json`: build_commit + graphify_version + recorded_at — the graph is never SHA-pinned; its LLM layer is non-reproducible). `--check --scope-files a,b,dir/` returns a pure-git diff-relevance verdict (exit 0 fresh / 1 stale): regen is needed only when the recorded-commit..HEAD diff intersects the next phase's scope or the graphify version changed — plain commit inequality would force a regen after every phase merge. `resolve_report` composes both: returns `graphify-out/GRAPH_REPORT.md` for `snapshot_context(project_context_path=…)` only when the report exists and provenance is fresh — the Step-2 bundle seam (copied bytes land as `context-bundle/project-context.md`, SHA-pinned via `snapshot_shas.project_context`).

## Worktree lifecycle (PR2)

Each worker gets `git worktree add` under `.planning/auto-pilot/worktrees/auto-pilot/iter-N/phase-P/…`. PM mutates `$ROOT` only through `WorktreeManager.apply_to_main` (`main-apply.lock`) via `git format-patch | git am --3way --trailer auto-pilot-{iter,phase,contract,idempotency}`. Conflict → `git am --abort`, increment `merge_attempts`; 3 failures → `merge_pivot_needed`.

## Reviewer sandbox (PR3, 4 layers)

1. Agent frontmatter `tools:` whitelist — best-effort
2. `hooks/pre-reviewer-write.sh` PreToolUse (`AUTO_PILOT_SUBAGENT_ROLE`) — blocks Edit/Write/MultiEdit outside `$AUTO_PILOT_OUTPUT_DIR` + Bash mutations. **Real wall.**
3. PM assert_reviewer_was_scoped — git status --porcelain empty after every reviewer return. **Real wall.**
4. `codex exec --sandbox read-only` — model-layer deterrent (not OS-level).

Parallel reviewers use `scripts/_reviewer_wrapper.py` (isolated env per subprocess — prevents env-var signal race). Reviewers also write `outputs/<role>/status.json` heartbeats (`scripts/_heartbeat.py:1`), surfaced by `scripts/orchestrator.py review-status`; codex review is bounded with ABSTAIN fallback (`scripts/codex_review_bounded.py:1`).

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

## Dispatch trust chain & evidence gates (run-3 hardening, 2026-06-10)

Three complementary layers that together make the contract dispatch path fail-closed:

### Entry gate — dispatch-contract-check (PR-A, 2026-06-12)

The PM follows this sequence before any reviewer dispatch (`agents/pm-orchestrator.md`):

```
write contract.json
→ write PM-SIGNATURE
→ orchestrator.py dispatch-contract-check --contract <contract.json>
→ creates/validates contract-check.json (contract hash + PM-SIGNATURE status)
→ _dispatch.prepare_subagent_ticket(contract_dir, worktree, subagent_role, ...)
→ dispatch with prompt markers:
     TICKET=<ticket_path>
     contract_dir=<contract_dir>
```

`hooks/dispatch-contract-gate.sh` derives the contract directory from those markers and rejects reviewer dispatch (`auto-pilot-codex-reviewer` / `auto-pilot-claude-reviewer`) during an active run when no `TICKET=` or `contract_dir=` marker is present — catching ad-hoc reviewer bypasses that skip the frozen-diff sha binding. Workers dispatch as `general-purpose` (non-reviewer type) but carry `TICKET=<contract_dir>/tickets/worker.json`, so the gate additionally DENIES a worker dispatch whose `context-bundle/learnings.md` is absent (D2 inject enforcement — `resolve_learnings` always writes that file, so absence means injection was skipped); other worker invariants are covered by the exit gate.

Regression pins: `tests/test_pm_protocol_contract_dispatch.py` asserts `dispatch-contract-check` appears before `prepare_subagent_ticket` in the protocol section, and that `TICKET={ticket_path}` / `contract_dir={contract_dir}` literals are preserved.

### Exit gate — evidence chain (run-3 residuals, shipped 2026-06-10)

`scripts/_evidence.py:assert_round_evidence(contract_dir)` — load-bearing gate for the run-3 bypass where phase 2 advanced to success with a missing reviewer ticket and empty reviewer output dir. Evidence chain that must hold for every latest-round dir before `phase-end --status success` can write state:

1. `review-input/frozen.diff` exists; recomputed SHA-256 == `review-input/frozen.diff.sha256` content.
2. Both `tickets/{codex-reviewer,claude-reviewer}.json` exist with `diff_sha256` equal to that value.
3. Both `outputs/{codex-reviewer,claude-reviewer}/review.json` exist, schema-valid, `contract_id` matches the round. Verdict requirement (per `scripts/_evidence.py` docstring lines 17–20, CLAUDE.md module table): claude-reviewer must be APPROVE; codex-reviewer may be APPROVE or honest ABSTAIN (verdict `ABSTAIN` + non-empty `reviewer_meta.abstain_reason`) — codex unavailability never blocks, a codex REJECT still does. Any APPROVE from either reviewer additionally requires `scope_check=PASS`.
4. `PM-SIGNATURE` exists and `_contract.verify_pm_signature(contract_dir)` passes — missing, unreadable, or tampered signature converts to `EvidenceError` (shipped PR#34, 2026-06-12). `scripts/_contract_check.py` is the single producer for `contract-check.json`; it records `pm_signature.verified`, `pm_signature.signature_sha256`, `pm_signature.contract_sha256`, and `pm_signature.manifest_sha256` so a stale or legacy artifact is detectable before dispatch. `hooks/dispatch-contract-gate.sh` also verifies the signature-status fields before its independent `PM-SIGNATURE` recomputation (PR#35).

`scripts/orchestrator.py cmd_phase_end` calls `_evidence.gate_phase_end(contracts_root)`, which internally locates the latest-round dirs and runs `assert_round_evidence` on each. Failure → exit 2, `BLOCKED` stderr, state untouched. `AUTO_PILOT_SKIP_EVIDENCE=1` escape hatch exists for unit tests that fabricate state without contract dirs (test-only, never for live runs).

Proven live in run-4 (2026-06-10/12): dual APPROVE with sha-bound evidence required before phase advanced; deliberate missing-trailer REJECT in phase 1 proved the round-2 recovery path.

### F-6 headless background-dispatch guard (deterministic, 2026-06-10)

`hooks/headless-sync-dispatch-guard.sh` (PreToolUse Task|Bash): under `HARNESS_HEADLESS=1`, denies `run_in_background=true` dispatch — the F-6 failure mode where a headless PM background-dispatched reviewers then exited, orphaning them. Guard wired in `hooks/hooks.json`. Self-test: `hooks/test_headless_sync_dispatch_guard.py`. Documented residual: Bash trailing-`&` backgrounding not covered (fuzzy detection, deferred deliberately).

## Headless timeout preservation (PR-B, 2026-06-12)

`scripts/headless-loop.py` timeout handling (`rc == 124`) is state-aware:

```
run_claude_session(...) returns rc
→ reload state
→ accumulate usage
→ if rc == 124:
     if state already records success OR active phase ended successfully:
         preserve state and return the recorded status (never overwrite)
     else:
         keep existing fail-closed timeout path (stash + mark failed)
```

Helpers: `_timeout_preserved_status(state_after)` checks `status == "success"` or `_completed_active_phase(state_after)` (active phase entry has `status=success` + `ended` timestamp). The phase-for-next-session helper (`phase_for_next_session(state)`) advances `current_phase + 1` only when the active phase completed successfully — initial `current_phase=0` renders as phase 1 in prompts.

Invariant: phase-end evidence gates remain the authority for success. Timeout preservation only applies when state already proves success before the wrapper timed out — it cannot turn stranded reviewer outputs into success.

Regression tests: `tests/test_headless_loop_recovery.py::test_timeout_preserves_terminal_success_state` and `::test_timeout_preserves_completed_phase_when_run_continues`.

## Routing ledger & model-tier assignment (Slice C, 2026-06-12)

### Module split

**`scripts/_ledger.py`** — IO layer + schema validation. Public API: `load_ledger`, `validate_ledger`, `save_ledger`, `build_record_from_round_dirs`, `append_phase_records`. Re-exports `evaluate_rebalance` from `_rebalance.py` for backward-compat callers. Schema: `schemas/routing-ledger.schema.json` (JSON Schema 2020-12; `p0_escaped` OPTIONAL boolean added).

**`scripts/_rebalance.py`** — pure rule engine. No ledger IO; config read via `_routing` (`_routing.model_rank` reads `model-routing.yaml` to resolve tier ranks). Operates on plain dicts only. `evaluate_rebalance(ledger, ladder, config)` returns proposed `rebalance_log` entries (never written unless `--apply`).

### Four rebalance rules

SoT for trigger wording: `skills/auto-pilot/references/model-routing.md`. Code enforcement: `scripts/_rebalance.py`.

| Rule | Trigger | Effect |
|------|---------|--------|
| `promote-2x-gate-fail` | last two consecutive fresh records both fail `gates_first_try` | propose model upgrade |
| `promote-real-p0` | any fresh record has `p0_escaped=True` | propose model upgrade |
| `trial-demotion-3x-clean` | last three consecutive fresh records all clean (`review_rounds==1`, first-try gate pass, `rejects_real==0`); a pending trial blocks a new demotion | propose one-tier trial demotion |
| `revert-trial` | any single failing record newer than the trial-demotion entry | propose revert to prior tier |

`revert-trial` takes precedence: when it fires for a group, promote rules are suppressed for that group in the same pass. At most one promote rule fires per group per call (double-promote prevention).

### Composite key convention

`ledger-rebalance --apply` writes `assignments` keyed by `"<role>/<task_class>"` (e.g., `"worker-primary/feature-multi-file"`). Plain role keys remain valid — `_current_model_for_group` checks composite key first, then plain role as fallback.

### Phase-end auto-append

`orchestrator.py cmd_phase_end` calls `_ledger.append_phase_records` after the evidence gate, before `_close_phase`, wrapped in `try/except`. On failure: one-line `_warn()`, continue. Ledger is telemetry — never a gate (`scripts/orchestrator.py`).

### v1 limitation (honest)

The contract schema (`schemas/contract.schema.json`, `additionalProperties:false`) carries no `role` or `task_class` fields. Auto-records from `append_phase_records` collapse into one group (`worker-primary/feature-multi-file`). Per-group rebalance is only meaningful for **hand-authored** ledger records. Role+task_class fields in the contract schema would fix this in v2.

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
