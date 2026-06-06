# autopilot-swarm SPEC

Canonical reference. Source of truth for PMs, workers, verifiers, reviewers.
Read this before editing any script under
`/Users/lyan/.claude/plugins/autopilot-swarm/scripts/` or any agent under
`/Users/lyan/.claude/plugins/autopilot-swarm/agents/`.

## Overview

`autopilot-swarm` is a tmux-hosted plugin that runs a long-lived multi-agent
loop against the caller's git repo. One **PM** process (`claude-opus-4-7`,
fixed) bootstraps knowledge, decomposes a user goal into milestones, dispatches
tickets, scores results, and reconciles a ledger. **Workers** (4–10, mixed
`claude` + `codex`) poll a per-worker inbox, atomically claim tickets via
`mv`, execute inside isolated `git worktree` checkouts, and emit diffs +
commit SHAs. An optional **swarm-verifier** sub-agent re-runs acceptance
checks on `verdict=merge` outputs for adversarial second-opinion.

The bus is filesystem-only: `.planning/autopilot/inbox/worker-<id>/` →
`.planning/autopilot/in_progress/` (claim via atomic rename) →
`.planning/autopilot/done/` (worker writes) →
`.planning/autopilot/scores/` (PM writes) → `.planning/autopilot/archive/`
(PM moves after scoring). Knowledge inputs live in
`.planning/autopilot/knowledge/synthesis.md` (cross-source theme synthesis,
T1–T15) and `.planning/autopilot/knowledge/roadmap.json` (milestones
M1–M6 with executable `success_criteria`).

**Round 3** exists because rounds 1–2 left material gaps: orphan agents
(`swarm-monitor.md`, `swarm-verifier.md`) not wired into `start.sh`; lock-dir
race in `run-pm.sh`; newest-first ticket starvation in `run-worker.sh`; no
schema validation on the bus; no `STOP` sentinel; no `CLAUDE.md`/`AGENTS.md`
at plugin root. Synthesis themes T1–T15 are the round-3 backlog; this SPEC
freezes the design those tickets must converge to.

## Components

### scripts/ (`/Users/lyan/.claude/plugins/autopilot-swarm/scripts/`)

| Path | Purpose |
|---|---|
| `start.sh` | Boot tmux session `autopilot-<basename>`, validate config schema, create per-worker worktrees, launch PM pane + N worker panes. |
| `stop.sh` | Send `C-c` to every pane in the session, then `kill-session`. `--purge` removes worktrees + branches. |
| `run-pm.sh` | PM loop: explore → bootstrap → goal-decompose → forever{score → ledger → dispatch}. Always `claude-opus-4-7`. |
| `run-worker.sh` | Per-worker poll loop. `mv` atomic claim from `inbox/worker-<id>/` to `in_progress/`. Calls `claude` or `codex` inside the worker's worktree. Commits diff. Moves to `done/`. |
| `bench.sh` | A/B/C benchmark of one task: swarm (ticket injection) vs `claude-opus-4-7` solo vs `codex gpt-5.5` solo. Writes `bench/<ts>/report.md`. |
| `prompts/pm-explore.md` | PM phase-0a prompt: dispatch `swarm-explorer` Task; produce `project-snapshot.md` + `project-files.json`. |
| `prompts/pm-bootstrap.md` | PM phase-0b: pull NotebookLM + Obsidian + Context7 + web; produce `synthesis.md` + `topics.json`. |
| `prompts/pm-goal-decompose.md` | PM phase-0c: emit `roadmap.json` (milestones, success_criteria). |
| `prompts/pm-dispatch.md` | Issue one ticket for worker-N. Schema-stamped JSON. Must avoid `scope_paths` overlap with in-flight tickets. |
| `prompts/pm-self-improve.md` | Every 4th dispatch (if `policy.self_improve_target` set), retarget ticket at the plugin itself. |
| `prompts/pm-score.md` | Score one done ticket. Writes `scores/<tid>.json` `{verdict, total, …}` via `Skill(quality-eval)`. |
| `prompts/pm-verify.md` | Independent verifier re-run for `verdict=merge`. Spawns `swarm-verifier` agent. |
| `prompts/pm-ledger.md` | Reconcile per-worker weights (incentive/penalty thresholds), cherry-pick merge-verdict commits. |

### agents/ (`/Users/lyan/.claude/plugins/autopilot-swarm/agents/`)

| Path | Purpose |
|---|---|
| `swarm-explorer.md` | Read-only stack/entry-point/doc-hierarchy mapper. Outputs `project-snapshot.md` + `project-files.json`. Wired via `pm-explore.md`. |
| `swarm-monitor.md` | Read-only health dashboard. **Currently orphaned** — not invoked from any script (T15). |
| `swarm-verifier.md` | Adversarial second-opinion verifier. Wired only through `pm-verify.md` prompt body (not direct script). |

## Ticket Lifecycle

State machine:

```
                +-- (PM dispatch) ----------+
                |                           v
       (none) -->  inbox/worker-<id>/T-*.json
                           |
                           |  worker-<id> poll
                           |  mv (atomic, single winner)
                           v
                   in_progress/T-*.json
                           |
                           |  worker runs engine, git add, commit
                           |  mv
                           v
                       done/T-*.json
                           |
                           |  PM pm-score.md → scores/<tid>.json
                           |  (if verdict=merge && verifier_enabled)
                           |    PM pm-verify.md → scores/<tid>.verify.md
                           |  PM mv
                           v
                     archive/T-*.json
```

**Atomic claim contract.** Producer (`pm-dispatch.md` rendered output) writes
to `inbox/worker-<id>/T-<ts>.json` via the PM `claude` CLI; consumers
(`run-worker.sh:26`) call `mv "$TICKET" "$IP"` — POSIX rename is atomic on
the same filesystem; the losing racer gets nonzero and `continue`s. See
synthesis T3.

**FIFO ordering.** Currently `run-worker.sh:19` uses `ls -t … | head -1`
(newest-first). Topic `ticket-fifo-oldest-first` (T11) replaces with
`ls -tr` or monotonic-id sort. Until merged, starvation risk on old tickets.

**Scope overlap rule.** `pm-dispatch.md` instructs the PM to read all in-flight
tickets (`inbox/*/*.json` + `in_progress/*.json`) and reject overlapping
`scope_paths`. Currently prose-only enforcement (T2). Topic
`pm-dispatch-overlap-guard` lifts it into `run-pm.sh` pre-write check.

**Bench injection.** `bench.sh:run_arm_swarm` writes directly to
`inbox/worker-<first_id>/T-bench-<ts>.json` bypassing the dispatch lock —
acceptable because bench arms run when PM is idle, but documented for
M2 lock-tightening work.

## Schemas

### ticket.json (current de-facto, no JSON Schema yet — topic `ticket-schema-json`)

| Field | Type | Notes |
|---|---|---|
| `id` | string | `T-YYYYMMDD-HHMMSS` |
| `topic` | string | Must match a `topics.json[].topic` slug |
| `milestone` | string | `M1`–`M6` slug or `"maintenance"` |
| `title` | string | imperative, ≤80 chars |
| `prompt` | string | self-contained; absolute paths; engine constraints |
| `knowledge_refs` | string[] | `knowledge/...` or `external:...` refs |
| `scope_paths` | string[] | files/dirs the worker may edit |
| `acceptance` | string[] | each entry = bash one-liner; `exit 0` == pass |
| `engine_hint` | enum | `claude` \| `codex` |
| `role` | enum | `architecture-review` \| `codegen` \| `general` \| `security` \| `verification` |
| `difficulty` | int | 1–5 |
| `issued_at` | string | UTC ISO8601 |
| `issued_by` | string | `pm` \| `bench` \| `user` |
| `worktree` | string | relative, e.g. `../<basename>-worker-3` |

Validator target: `schemas/ticket.schema.json` (TBD — topic
`ticket-schema-json`). Worker preflight: `worker-preclaim-schema-validate`.

### score.json (TBD — topic `score-output-schema`)

Required-by-code today (referenced in `run-pm.sh:111-113`):

| Field | Type | Notes |
|---|---|---|
| `verdict` | enum | `merge` \| `changes` \| `reject` |
| `total` | number | aggregate score |

`pm-ledger.md` reads further fields (per-dimension weights, deltas); exact
shape is not asserted. Topic `score-output-schema` formalizes
`schemas/score.schema.json`.

### verify.json (TBD — topic `verifier-evidence-fields`)

Required by `pm-verify.md` + `swarm-verifier.md` body (current prose-only):

```json
{"verifier": {
  "passed": true,
  "reproductions": ["..."],
  "downgraded_to": null,
  "notes": "..."
}}
```

Topic `verifier-evidence-fields` (synthesis T6) extends with
`evidence: { cmd_output, files_checked, diff_sha }` and pins it as
`schemas/verify.schema.json`.

## Failure Modes

| # | Failure | Blast radius | Mitigation status |
|---|---|---|---|
| F1 | PM `dispatch.lock.d` mkdir-lock goes stale (process killed mid-write); after 30 retries `run-pm.sh:22` `rm -rf` blindly — concurrent writer's tmp can be lost (T3) | One dispatch dropped per stale event; cross-worker ticket starvation | OPEN — topic `flock-based-pm-lockdir` (M2) |
| F2 | Atomic-claim race between two workers polling the same inbox path (T3) | First mover wins, loser `continue`s — currently handled at `run-worker.sh:26` via `mv` nonzero guard | DONE (commit `6ad2b4c`) |
| F3 | `scope_paths` overlap between two in-flight tickets (T2) — prose-only guard in `pm-dispatch.md`; PM may issue overlapping work that produces merge conflicts at cherry-pick time | Two workers' diffs touch same lines → wasted compute + manual conflict resolution | OPEN — topic `pm-dispatch-overlap-guard` (M2) |
| F4 | PM phase failure infinite-loops with no backoff: `run-pm.sh:70,83,95` `sleep 30; exec "$0"` (T4) | Cost runaway if external API permanently down; no kill switch | OPEN — topic `retry-backoff-loop` (M3); also `stop-sentinel-honor` |
| F5 | `bench.sh:49` `while [ ! -f score.json ]; do sleep 10; done` polls forever if swarm hangs (T4) | Bench process pinned indefinitely; tmux pane non-responsive | OPEN — topic `bench-poll-timeout` (M3) |
| F6 | Newest-first ticket selection in `run-worker.sh:19` (`ls -t \| head -1`) starves older tickets if backlog grows faster than throughput (T11) | Old high-value tickets never executed; FIFO contract violated | OPEN — topic `ticket-fifo-oldest-first` (M2) |
| F7 | Headless `claude -p` cannot reach `Skill(quality-eval)` in `pm-score.md` — silent skill miss returns degraded score (T6, T12) | Every score under-credits worker → ledger weights collapse → workers paused | OPEN — topic `preflight-skill-check` (M5) |
| F8 | Cross-worktree cherry-pick race during PM ledger merge (T14) | Two `merge`-verdict commits applied concurrently can corrupt index | OPEN — topic `merge-lock-flock` (M2) |
| F9 | Orphan agents `swarm-monitor.md` + `swarm-verifier.md` unreachable from any script entry point (T7, T15) | UX: user thinks monitor exists but `/swarm-monitor` does nothing; verifier never spawned despite `policy.verifier_enabled` (claimed via prompt body only) | OPEN — topics `swarm-monitor-wire-tmux`, `curate-orphan-agents` (M4, M5) |
| F10 | `STOP` sentinel not honored — neither `run-pm.sh` nor `run-worker.sh` nor `bench.sh` check for `.planning/autopilot/STOP` (T4, T15) | No clean kill-switch; user must `Ctrl-C` panes or `kill-session` | OPEN — topic `stop-sentinel-honor` (M3) |
| F11 | `pm_call` (`run-pm.sh:46`) merges stdout + stderr into one log → grepping errors requires noise filtering (T13) | UX/observability: harder root-cause | OPEN — topic `pm-stderr-separate-log` (M4) |
| F12 | Ticket JSON written by PM has no schema validation; a malformed prompt or scope_path slips through and worker claims an unrunnable ticket (T5) | Wasted engine call, polluted `done/` + `scores/` | OPEN — topics `ticket-schema-json` + `worker-preclaim-schema-validate` (M2) |

Reference: `.planning/autopilot/knowledge/synthesis.md` §T1–T15;
roadmap milestones in `.planning/autopilot/knowledge/roadmap.json`.

## Invariants

- **I1.** PM never touches an `in_progress/` file mid-claim. Workers own
  every path under `in_progress/T-*.json` from the moment their `mv` from
  inbox succeeds until they `mv` to `done/`. PM only reads `in_progress/`
  (for overlap detection in `pm-dispatch.md`).
- **I2.** Worker validates ticket JSON against `schemas/ticket.schema.json`
  (topic `worker-preclaim-schema-validate`) **before** the atomic `mv`. A
  malformed ticket is moved to `archive/<tid>.invalid.json` and not
  claimed.
- **I3.** `STOP` sentinel at `.planning/autopilot/STOP` is honored by
  every long-running script: `run-pm.sh` exits cleanly between loop
  iterations; `run-worker.sh` exits after current ticket completes;
  `bench.sh` aborts the polling wait. Topic `stop-sentinel-honor`.
- **I4.** `scope_paths` of any two **active** tickets (state `inbox` or
  `in_progress`) must be disjoint. Disjoint = no path A is a prefix of
  path B and vice versa. Enforced in `run-pm.sh` pre-write check (topic
  `pm-dispatch-overlap-guard`), not just `pm-dispatch.md` prose.
- **I5.** Every shell script in `scripts/` passes `bash -n` (syntax check).
  Already an exit criterion in `roadmap.json`.
- **I6.** Ticket JSON written by PM is written via tmp + `mv` rename
  (atomic on same filesystem); never `cat > <inbox-path>` directly. Topic
  `atomic-tmp-mv-ticket-write`.
- **I7.** Per-worker inbox is FIFO: oldest ticket claimed first
  (`ls -tr | head -1` or monotonic-id sort). Topic
  `ticket-fifo-oldest-first`.
- **I8.** PM model is pinned to `claude-opus-4-7` (`start.sh:42` schema
  guard rejects any other value). Worker engines + models are validated
  by `start.sh:47-50`.
- **I9.** Verifier output schema includes `evidence` (cmd_output,
  files_checked, diff_sha) when present. Topic `verifier-evidence-fields`.

## Open Questions

1. **Q1 — Should the verifier downgrade verdict in-place, or emit a
   sibling file?** Today `swarm-verifier.md` says "Update the score file
   in place (preserve all existing fields)" but that conflates score
   provenance (PM) with verification provenance (independent agent). Topic
   `verifier-evidence-fields` (T6) needs to decide: in-place mutation vs
   `scores/<tid>.verify.json` sidecar. Ledger reconciliation
   (`pm-ledger.md`) currently reads only `scores/<tid>.json`.

2. **Q2 — Where does ticket schema validation live: producer-side
   (`run-pm.sh`) or consumer-side (`run-worker.sh`)?** Topic
   `worker-preclaim-schema-validate` (T5) puts it consumer-side, but
   producer-side fail-fast saves an engine call. Round-3 decision: do
   both, or single source of truth? Cross-ref topic `ticket-schema-json`.

3. **Q3 — How does the self-improve loop break recursive ownership?**
   `policy.self_improve_target` points the swarm at its own plugin dir
   (`/Users/lyan/.claude/plugins/autopilot-swarm`). When the PM edits
   `run-pm.sh` while running from `run-pm.sh`, what's the safe reload
   contract? Current code uses `exec "$0"` (T4), but that re-execs the
   *old* in-memory script if the file has been overwritten only partially.
   Topic `retry-backoff-loop` touches this but does not solve it. May
   need a sibling `pm-supervisor.sh` that owns reloads.

4. **Q4 — Does `swarm-monitor` belong as a tmux window (always-on) or as
   an on-demand sub-agent (Task tool)?** Synthesis T15 says "permanent
   tmux window"; the agent frontmatter says "Spawn via Task tool". Topics
   `swarm-monitor-wire-tmux` (M4) vs `curate-orphan-agents` (M5) disagree
   implicitly. Need to pick before either ships.

5. **Q5 — What's the cost ceiling per PM loop iteration?** No budget
   currently tracked. README must add a cost projection table (topic
   `readme-cost-projection`, T10), but the loop itself does not stop on
   $-spent. Open: do we add an `agent-scores.json` cost field and abort
   on threshold, or rely solely on the (TBD) `STOP` sentinel and user
   judgement?
