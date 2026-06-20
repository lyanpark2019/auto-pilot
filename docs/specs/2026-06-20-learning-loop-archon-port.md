# Learning-Loop → Archon Port — benefit-measured PoC (v4, Claude + codex critics folded)

> Durable re-runnable spec. Code is the output. This is the asset.
> Status: PLAN v4 — READY-TO-IMPLEMENT. Claude critique (2 P0 + 2 P1 + 2 P2) + codex round-1
> (3 P0 + 3 P1 + 1 P2, UNSOUND) + codex confirm (all 7 RESOLVED, 1 new P1 OFF-env-scope) all folded.

## Goal

Prove or **kill** one falsifiable thesis on Archon: a harness that has CAPTURED+MINED a recurring
defect-class on earlier runs catches that same class at a higher round-1 rate on a later,
structurally-related diff than the identical harness with memory disabled
(`AUTO_PILOT_DISABLE_LEARNINGS=1`). Targets the ONE capability Archon categorically lacks for the
autonomous case — durable cross-run defect memory. Deliverable = a kill-or-proceed verdict, NOT a feature.

## Why this is the right target

Cross-model *review* ports to Archon as pure YAML (proven:
`~/.archon/workflows/xmodel-adversarial-review.yaml`) but its marginal value on EASY code measured weak
(n=4). HOWEVER cross-model value is **difficulty-dependent**: on this very plan, codex caught 6 blind
spots Claude missed (UNSOUND verdict) — cross-model is strong on HARD reasoning artifacts. The learning
loop is the differentiator Archon has zero equivalent for. The "port" is mostly "Archon shells out to
auto-pilot Python," so the strategic fallback (if benefit fails) ≈ the architecture: *Archon CALLS
auto-pilot, do not port deeper.*

## Architecture (grounded, file:line verified by both critics)

**PORT BOUNDARY.** Cross-model REVIEW = pure YAML. MINE/PROMOTE/INJECT cannot be YAML — Archon has no
*non-opt-in* cross-run memory:
- `artifactsDir` per-run: `archon executor.ts:257` (`runs/<workflowRunId>`).
- node outputs persist only to per-run SQLite; `LoopNode` within-run.
- Archon DOES have opt-in `persist_sessions`/`persist_session` (`workflow.ts:89`, `dag-node.ts:191`)
  resuming provider sessions from DB (`dag-executor.ts:3323`) — **must be OFF** for a clean A/B;
  `context: fresh` bypasses it (`dag-executor.ts:3299`). (codex P2.)
- ONLY durable cross-run channel = filesystem ledger at a stable path.

**DURABLE SUBSTRATE (reused; minimal new flags).** Ledger
`~/.claude/projects/<slug>/improvements/<fp>.json` (`_improvement.py:118-122`). **CRITICAL (codex P1-4):**
`<slug> = project_slug(repo_root)` embeds the ABSOLUTE repo/worktree path (`_improvement.py:98,122`), and
Archon CLI DEFAULTS to timestamped worktree isolation (`workflow.ts:513,717,780`) → same `$HOME` is NOT
enough; each worktree yields a different slug → ledger diverges. **MUST pin `worktree.enabled: false`
AND pass a stable canonical `--repo-root`** so every run resolves the same ledger dir. `bump_or_create`
holds `fcntl.LOCK_EX` across RMW + atomic temp+rename (`_improvement.py:153-167,342,368`).

**RUN_ID AXIS.** `distinct_runs = len({e['run_id']...})` (`_improvement.py:314`); scan keys on the line's
OWN run_id (`learning_miner.py:162-167`). Archon `$WORKFLOW_ID` is per-run TEXT substitution
(`executor-shared.ts:441`) → **never use it as run_id** (inflates distinct_runs on same-diff re-runs).
run_id derives from the reviewed work unit (commit SHA / diff hash). **codex P0-2:** `run_miner` forces
DRY-RUN (no ledger write) when `.planning/auto-pilot/state.json` lacks a non-empty `run_id`, EVEN IF
jsonl lines carry one (`learning_miner.py:297,303`) → the mine node MUST write `state.json` with RUN_ID
before invoking the miner (or use a new `--run-id` flag), and the test MUST assert a physical ledger
file appears.

**INJECTION MUST NOT SPOIL (codex P0-1 — the experiment-killer).** `render_learnings` prints the ticket
pattern + evidence snippets (`_learnings.py:176,199`). If injected verbatim, the prompt NAMES the defect
and the A/B measures "the prompt said the class," not learning. **PoC uses a SANITIZED render: generic
class-level nudge ONLY** ("prior runs found `<class>` defects in this scope — check for them"), with NO
prior issue title, evidence JSON, file path, run id, line, or snippet. The oracle scores a catch ONLY
when the reviewer finding's `class == golden` AND its `file` matches the hidden golden-defect file
(location match, not class-anywhere).

**DATAFLOW.** capture-diff → INJECT bash node (sanitized `resolve-learnings`, reads durable ledger via
`--ledger-dir`) → ONE pinned claude reviewer (`context: fresh`, reads `diff.patch` + sanitized
`learnings.md`, `output_format` emits `file`+`class`) → CAPTURE+MINE bash node (`trigger_rule: all_done`).
**TRAIN/TEST SPLIT (codex P0-3):** during held-out SCORING the mine node is DISABLED and the ledger is a
per-arm COPY of a frozen stage-A-seeded ledger; driver asserts the scoring ledger hash is unchanged
across the scored set (no eval case contaminates a later one).

**MEASUREMENT.** Driver runs ON vs OFF over byte-identical frozen seed diffs. OFF =
`AUTO_PILOT_DISABLE_LEARNINGS=1` **inlined ONLY on the inject bash node's `resolve-learnings` command**
(`AUTO_PILOT_DISABLE_LEARNINGS=1 python3 ... resolve-learnings ...`) → `resolve_learnings` writes
`_BLIND_MARKER` (`_learnings.py:233-239`). NOT the Archon CLI subprocess env — the Claude provider copies
`process.env` (`claude/provider.ts:88,865`) so a subprocess-wide OFF env would also reach the reviewer and
break "arms differ in exactly one bit" (codex confirm P1). There is no node `env` field (`dag-node.ts:140`),
so the toggle lives in the command string the driver emits. Reviewer node pinned `allowed_tools: [Read]`
(matches xmodel `xmodel-adversarial-review.yaml:27`). Deterministic oracle scores by class+location,
SHA-256-logs every `review.json`. Verdict = paired catch-rate delta + CI, killable.

## Global constraints (both critics' fixes folded)

- `PROMOTION_THRESHOLDS['reviewer-finding']=2` distinct runs (`learning_miner.py:26-32`); PoC slice uses `is_promotable` (≥2); full `_promotion` FSM CUT.
- Adapter emits a `class` from `REVIEWER_FINDING_CLASSES` (`learning_miner.py:58-66`) else phrasing variance fragments the fingerprint → distinct_runs never reaches 2.
- run_id = `git rev-parse HEAD` clean tree, fallback `shasum(diff.patch)`, NEVER `$WORKFLOW_ID`.
- Mine node writes `.planning/auto-pilot/state.json` `{run_id: RUN_ID}` BEFORE the miner (codex P0-2); test asserts a real ledger file is created/bumped.
- Adapter mapping: REJECT-only (`_capture_reviews.py:149`), `severity∈{P0,P1}` (`:159`), `issue←finding.title` (rename; xmodel schema has `title`), `candidate_asset=null`, dedupe on `canon_key=json.dumps(line,sort_keys=True)` (`:186-189`). Adds `file` (repo-relative) + `class`.
- **Injection is SANITIZED**: generic class nudge only; NO title/evidence/file/line/snippet (codex P0-1). New `--sanitized` mode on resolve-learnings keeps selection (gate + scope-match) but strips render to class names.
- **Ledger path is pinned stable**: `worktree.enabled: false` in the YAML + a stable canonical `--repo-root` on BOTH mine and inject (codex P1-4). Inject reads the durable ledger via a new `--ledger-dir` on resolve-learnings (codex P1-5; currently only `--repo-root/--scope/--dest-dir`, always `ledger_dir(repo_root,None)` `_learnings.py:240`).
- **Train/test isolation** (codex P0-3): scoring runs against a per-arm COPY of a frozen stage-A-seeded ledger; mine DISABLED during scoring; driver asserts scoring-ledger SHA unchanged across all scored cases.
- **OFF toggle** = `AUTO_PILOT_DISABLE_LEARNINGS=1` inlined ONLY on the inject node's `resolve-learnings` command — NOT the CLI subprocess env (leaks into the Claude provider, `claude/provider.ts:88,865`), NOT a node `env` field (none exists, `dag-node.ts:140`). ON arm = command without the prefix. (codex P1-6 + confirm P1.)
- **Clean-session A/B** (codex P2): reviewer node `context: fresh` + `allowed_tools: [Read]`; no workflow-level `persist_sessions`; driver asserts no `node_session_resumed` event in either arm.
- codex `output_format` strict-schema: every prop in `required`. `class` always-present with a `"none"` sentinel the adapter drops; `file` always-present.
- A/B arms differ in EXACTLY one bit: real (sanitized) content vs `_BLIND_MARKER` in `learnings.md`. Same model+provider (ONE claude reviewer, fresh ctx), SHA-pinned `seed.diff`, same scopes. Ticket present in BOTH arms' (copied) ledger; OFF does not read it.
- Significance: Fisher exact one-sided + McNemar on paired outcomes; report catch-rate delta + 95% CI, never bare p.
- Noise guardrail (kill if violated): `noise_rate_ON − noise_rate_OFF ≤ +0.10` on clean holdout.
- **Anti-saturation band**: a test diff enters the scored set ONLY if OFF catch-rate ∈ [0.30,0.70] in pilot (fix for the cross-model 100/100 saturation).
- **ONE effect size**: minimum-meaningful = +0.20 = the PROCEED bar; power N to +0.20; budget McNemar discordant-attrition (effective N < pairs; estimate discordant fraction in pilot, re-derive N).
- **Oracle scores class+location**: catch only when finding `class==golden` AND `file==golden file` (codex P0-1). No LLM; SHA-256 recomputable.
- `jsonschema`/`referencing` hard imports (`_improvement.py:32`); Archon host needs `python3` + deps on `PYTHONPATH`, `scripts/` importable; pin interpreter (a HOME-override hid `referencing` before — r1-phrasing memory).

## File structure

- `<archon>/.archon/workflows/learning-loop-review.yaml` — PoC workflow. `worktree.enabled:false`; capture-diff + inject(bash) + ONE pinned claude reviewer (`context:fresh`) + capture-mine(bash, `trigger_rule:all_done`, DISABLED during scoring). All git/python shelled out.
- `<archon>/.archon/scripts/archon_review_to_jsonl.py` — ~40-line adapter. review.json → critic-rejections jsonl per mapping rules. Imports only `REVIEWER_FINDING_CLASSES` (or frozen copy + drift test).
- `<archon>/.archon/scripts/run_id_from_diff.sh` — stable RUN_ID (`git rev-parse HEAD`, fallback `shasum`), NOT `$WORKFLOW_ID`.
- `<auto-pilot>/scripts/learning_miner.py` — REUSED; **+ `--run-id` flag** OR mine node writes state.json first (codex P0-2). MINE phase.
- `<auto-pilot>/scripts/_improvement.py` — REUSED VERBATIM. Durable ledger.
- `<auto-pilot>/scripts/_resolve_learnings_cli.py` + `_learnings.py` — **+ `--ledger-dir`** (codex P1-5) and **+ `--sanitized` render mode** (codex P0-1). INJECT phase. Writes `<dest-dir>/context-bundle/learnings.md`.
- `<auto-pilot>/evals/cases/learnings-ab/archon_ab_driver.py` — ON/OFF driver: sets OFF env on the Archon subprocess, frozen per-arm ledger copies, mine-disabled scoring, SHA-logs, scores via oracle, emits paired table + Fisher + McNemar + delta CI + ledger-hash assertions.
- `<auto-pilot>/evals/cases/learnings-ab/oracle.py` — deterministic class+location scorer + noise count. Byte-stable.
- `<auto-pilot>/evals/cases/learnings-ab/seeds/` — frozen SHA-pinned fixtures: stage-A training (≥2/class), stage-B held-out (same class, different file/shape, ONE hidden golden defect with known file), clean holdout, 1 negative-control class. Each records the golden (class,file) for the oracle.
- `<auto-pilot>/evals/cases/learnings-ab/spec.md` — UPGRADED: powered N, [0.30,0.70] band, sanitized-injection rule, train/test split, kill criteria.

## Tasks (measurement-integrity first, then PILOT kill gate, then powered run)

### Task 1 — Design note (port boundary, run_id, ledger-stability, anti-spoiler)
Deliverable: `evals/cases/learnings-ab/design.md` with file:line for: no non-opt-in cross-run memory + persist_sessions must be off (executor.ts:257, dag-executor.ts:3299/3323); `$WORKFLOW_ID` per-run (executor-shared.ts:441); ledger slug embeds repo path + Archon worktree-isolation default → pin `worktree.enabled:false` + stable repo-root (_improvement.py:98,122, workflow.ts:513); miner dry-run gate (learning_miner.py:297,303); render spoiler hazard (_learnings.py:176,199). States same-host/shared-`$HOME`+pinned-repo-root as the precondition and multi-container as a KNOWN GAP.
Test: every citation resolves; reviewer confirms no invented Archon feature.

### Task 2 — Diff-identity run_id helper
Deliverable: `run_id_from_diff.sh`. Test: same committed diff twice → identical RUN_ID; one-byte mutation → different; covers clean-tree `git show` branch; assert RUN_ID ≠ `$WORKFLOW_ID`.

### Task 3 — `--run-id` flag on the miner (or state.json writer) + ledger-write proof (codex P0-2)
Deliverable: miner accepts `--run-id` that satisfies the non-dry-run gate without a pre-written state.json (preferred), OR a documented mine-node step that writes `.planning/auto-pilot/state.json {run_id}` first.
Test: run the miner over a jsonl with run_id=X via the new path → a PHYSICAL ledger file is created/bumped at the resolved ledger dir (assert file exists + distinct_runs reflects X). Without the flag/state, the same input stays dry-run (regression proof of the gate).

### Task 4 — `--ledger-dir` on resolve-learnings (codex P1-5)
Deliverable: `_resolve_learnings_cli.py` + `_learnings.py` accept `--ledger-dir` overriding `ledger_dir(repo_root,None)`.
Test: seed a ticket in a temp ledger dir; `resolve-learnings --ledger-dir <tmp> --dest-dir <d>` selects it; without the flag it reads the default and does NOT see the tmp ticket.

### Task 5 — `--sanitized` render mode (codex P0-1)
Deliverable: resolve-learnings `--sanitized` keeps selection (gate + scope-match) but renders ONLY a generic class-level nudge — NO title, evidence, file, run id, line, or snippet.
Test: a ticket whose evidence contains the literal defect text → sanitized `learnings.md` contains the class name and a generic instruction but NONE of: the issue title, the evidence string, the file path, any line number. Assert via substring checks against the known leaky fields.

### Task 6 — `archon_review_to_jsonl` adapter
Deliverable: ~40-line adapter (REJECT-only, P0/P1-only, `title→issue`, `class` from vocab, `file` repo-relative, `candidate_asset=null`, run_id from `RUN_ID`, canon_key dedupe; drops `"none"` sentinel class/empty file).
Test: REJECT review.json with one off-by-one P1 (`class='off-by-one'`, `file=x.py`) + one P2 → exactly one JSONL line, P2 dropped, passes the miner's `_iter_jsonl_dicts` → one Observation. Re-run → ZERO new lines. Real `learning_miner.py --json` (via Task 3 path) → ticket with expected fingerprint + a physical ledger file.

### Task 7 — Cross-run accumulation WITHOUT Archon + ledger-stability check (codex P1-4)
Deliverable: integration test: adapter+miner twice over TWO stage-A diffs of the SAME class, DISTINCT run_ids, against a temp ledger dir pinned by an explicit repo-root → distinct_runs 1→2, `is_promotable`. Plus a unit asserting two DIFFERENT repo-root paths resolve to DIFFERENT slugs (documents the worktree-divergence hazard the pinning fixes).
Test: after run 2 `--json` reports `promotable_count≥1`; re-run run 2's SAME diff/run_id → distinct_runs stays 2 (idempotent). Differing repo-root → differing ledger dir (assert).

### Task 8 — Deterministic class+location oracle + SHA-logging (codex P0-1)
Deliverable: `oracle.py` — review.json + golden (class,file) → caught iff some finding has `class==golden AND file==golden file`; + noise count; driver SHA-256-logs every review.json.
Test: golden fixtures (catch at right file / right class wrong file / P2 noise) → caught True/False/False + noise exact; SHA recompute matches.

### Task 9 — Wire the Archon workflow YAML (all P0/P1 folded)
Deliverable: `learning-loop-review.yaml` — `worktree.enabled:false`; capture-diff → inject (`resolve-learnings --sanitized --ledger-dir <durable> --repo-root <stable> --dest-dir $ARTIFACTS_DIR --scope <file>...`) → ONE claude reviewer (`context:fresh`, `allowed_tools:[Read]`, reads diff.patch + `$ARTIFACTS_DIR/context-bundle/learnings.md`, emits `file`+`class`) → capture-mine (writes state.json + adapter + miner, `trigger_rule:all_done`; a `SCORING=1` env gate disables it during held-out scoring). No `persist_sessions`. OFF arm = the inject command is prefixed `AUTO_PILOT_DISABLE_LEARNINGS=1` (inline, not subprocess-wide). `$WORKFLOW_ID` for logging only.
Test: run once on a seeded stage-A diff (mine ON), pinned repo-root, same-host. Assert (a) sanitized learnings.md exists + leaks nothing, (b) jsonl ≥1 line, (c) the DURABLE ledger gained a ticket, (d) no empty_run_id, (e) no `node_session_resumed` event. Re-run xmodel smoke → forked schema parses on both providers.

### Task 10 — A/B driver + frozen-ledger train/test split + **headroom pilot = kill gate** (codex P0-3, P1-6; Claude P1-2)
Deliverable: `archon_ab_driver.py` — seeds a frozen stage-A ledger ONCE, copies it per arm/pair, runs the workflow with mine DISABLED (`SCORING=1`) for scoring, OFF arm via `AUTO_PILOT_DISABLE_LEARNINGS=1` inlined ONLY on the inject command (NOT subprocess-wide — would leak into the reviewer, codex confirm P1). PILOT FIRST: ~8 OFF-only stage-B diffs; keep only OFF catch-rate ∈ [0.30,0.70]; require ≥1 class with an actual OFF-miss→ON-catch on ≥2 discordant pairs before any powered run.
Test: pilot lists per-diff OFF catch-rate + admitted subset; ON/OFF over same seed use byte-identical diff.patch (equal SHA); scoring-ledger SHA identical across all scored cases (no contamination); ON arm asserts ≥1 ticket selected (not silently blind). No mid-range class OR no OFF-miss→ON-catch → emits **INCONCLUSIVE/KILL** (accepted informative outcome → fallback). Deliberately-saturated fixture set → that branch fires.

### Task 11 — Powered A/B + kill-or-proceed verdict (only if pilot passes)
Deliverable: on N calibrated paired stage-B diffs (N powered to +0.20 w/ McNemar attrition budget) + clean holdout + 1 negative control → `verdict.json`: catch_rate_ON/OFF, paired delta + 95% CI, Fisher p, McNemar p, noise delta, negative-control delta, ledger-hash log. PROCEED iff delta≥+0.20 ∧ CI excludes 0 (Fisher ∧ McNemar) ∧ noise≤+0.10 ∧ negative control flat ∧ a COLD re-run on a fresh seed set reproduces sign+magnitude; KILL if delta≤0 / CI includes 0 / noise>+0.10 / negative control lifts / ON-arm blind / ledger hash drifted; KEEP-DEFERRED only on narrow ambiguity.
Test: `verdict.json` validates + recomputable from SHA-logged set. Synthetic ON==OFF dataset → MUST emit KILL.

## Scope cuts (restore IF the A/B proceeds)
PROMOTE FSM (`_promotion.py`; slice uses `is_promotable`); ApprovalNode human promotion (automation IS the differentiator); provenance HMAC (present-but-untested, host-local attest.key gap); demotion/quarantine (no down-vote signal); doom-loop/insight scanning (only reviewer-finding tickets seeded); review-codex as a 2nd SCORED reviewer (A/B pins one — memory axis, not cross-model); multi-host/container ledger (KNOWN GAP: flock host-local + advisory, per-container `$HOME`/slug diverges → needs Postgres/server ledger); ledger GC.

## Unresolved forks (PM defaults; human can override)
1. **run_id binding** — DEFAULT commit SHA clean-tree, diff-hash fallback. Override if Archon runs operate on uncommitted diffs.
2. **Ledger durability vs Archon execution model** — DEFAULT same-host + `worktree.enabled:false` + stable repo-root (PoC). Multi-container/host → needs server-mediated ledger before shipping. **Make-or-break for real deployment, not for the measurement.**
3. **Port-deeper vs Archon-calls-auto-pilot** — decided BY the A/B result. If benefit weak → keep the loop in auto-pilot, Archon CALLS it (≈ current architecture).
4. **Class emission** — DEFAULT extend reviewer prompt to require `class`+`file` (R1-safe); codex strict-schema → `"none"`/empty sentinels the adapter drops.
5. **Miner persistence path** — DEFAULT add `--run-id` flag (Task 3, cleaner+testable) over writing state.json from the node. Override if a source edit to learning_miner.py is unwanted (then node writes state.json).

## Critic fixes applied
**Claude v1→v2:** P0-1 schema-fork (`file`+`class`); P0-2 INJECT entrypoint (`orchestrator.py resolve-learnings`); P1-1 single effect +0.20; P1-2 headroom pilot gate; P2-1 run_id commit-SHA; P2-2 ON-blind guard.
**codex v2→v3 (verdict UNSOUND→addressed):** P0-1 sanitized render + class+location oracle (anti-spoiler); P0-2 miner `--run-id`/state.json + physical-ledger-write test (dry-run gate); P0-3 frozen-ledger train/test split + hash-unchanged assertion (eval contamination); P1-4 pin `worktree.enabled:false` + stable repo-root (slug embeds worktree path); P1-5 `--ledger-dir` on resolve-learnings; P1-6 OFF via subprocess env, not invented node `env`; P2 `context:fresh` + no `persist_sessions` + assert no session resume.
**codex confirm v3→v4:** all 7 prior RESOLVED; new P1 — OFF env must be inlined ONLY on the inject command (subprocess-wide leaks into the Claude provider, `claude/provider.ts:88,865`) + reviewer `allowed_tools:[Read]`.
