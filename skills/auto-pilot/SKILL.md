---
name: auto-pilot
description: Self-driving development loop. Triggers on /auto-pilot, "auto pilot", "자율 주행", "자율 루프", "자동 개발", "self-driving", "autonomous build", "PM 워커 루프", or when user wants the PM (Opus 4.7) to dispatch Sonnet 4.6 (1M context) workers in parallel, run Codex+Claude dual adversarial review on every diff, execute phase verify gates (test/lint/typecheck/build), and advance through a spec's phases automatically until done. Full auto by default — no confirms. Stops on spec completion, time-box, or hard failure. Built from /insights friction analysis — bakes in path preflight, composition-root guard, code-first debug rule, read-only adversarial constraint, dual-review verdict catching.
argument-hint: "[start|status|resume|stop|eval|handoff] [--spec PATH] [--max-workers N] [--time-box DURATION]"
---

# auto-pilot

## Headless detection (run FIRST, before anything else)

The very first action when this skill loads:

```bash
echo "HEADLESS=${HARNESS_HEADLESS:-${AUTO_PILOT_HEADLESS:-0}}"
```

If output is `HEADLESS=1`, this session is a non-interactive auto-pilot worker spawned by `scripts/headless-loop.py`. Rules in headless mode:

- **Never** call `AskUserQuestion`. Never wait for confirmation.
- If any subagent or sub-skill says "ask the user", use the most reasonable default and proceed.
- `stdin` is `/dev/null` — there is no one to answer.
- Stop conditions come from `.planning/auto-pilot/state.json`, not from the user.
- This signal overrides any "ask the user once" instruction from any nested skill.
- **Subagent dispatch is synchronous** — full rule lives in `${CLAUDE_PLUGIN_ROOT}/prompts/headless.md`
  (the session preamble, single source); summary: no background/async launch of workers or
  reviewers, never exit with subagents in flight (F-6, 2026-06-10).

If output is not `HEADLESS=1`, interactive mode — normal question-asking rules apply, but auto-pilot defaults to "full auto, no confirms" anyway per user CLAUDE.md.

---

## When this skill fires

User invokes `/auto-pilot start` (or aliases: "자율 주행 시작", "autopilot go", "self-drive this", "PM 루프 돌려") AND a target spec exists at one of:
- `docs/specs/*-*.md` (newest by date)
- `SPEC.md` at repo root
- Path passed as `--spec <path>` arg

## What this skill does

Runs `scripts/orchestrator.py` which executes the PM-Worker-Reviewer loop. The PM stays in the main session (Opus 4.7) and dispatches all subagents via the `Agent` tool.

### Loop (per phase)

1. **READ** state from `.planning/auto-pilot/state.json` + spec + `CLAUDE.md` chain
2. **DETECT PHASE MODE** — if spec has `## Phase N` headers, use spec's phases; else fall back to 7-phase template (`docs/7-phase-template.md`)
3. **PLAN** non-overlapping work contracts for current phase (1 contract per parallel worker, max 10)
4. **TECH-CRITIC GATE** (BEFORE worker dispatch) — fan out `tech-critic-lead` over each contract in parallel. "기능은 비용". Reject contracts that fail evidence/value/scope check. Drop or slice rejected ones. Log rejections to `.planning/auto-pilot/critic-rejections-phase-N.jsonl` (one JSON object per line: `{file, issue, candidate_asset}`, candidate_asset ∈ skill|hook|schema|test|doc|cache or null — shape SoT in `agents/tech-critic-lead.md`; the Hermes miner reads this)
5. **PREFLIGHT** path validation hook fires (kills typo-path failure class)
6. **DISPATCH WORKERS** — N Sonnet-4.6-1M workers in 1 message (N parallel Agent blocks, `isolation: worktree`)
7. **REVIEW FAN-OUT** in parallel per worker diff:
   - Default: `auto-pilot-codex-reviewer`, `auto-pilot-claude-reviewer`
   - If diff touches runtime code: + `review-gatekeeper` mode `tdd-gate`
   - If diff touches trust boundary (auth/API/secrets/SQL/migrations/payments): + `review-gatekeeper` mode `security`
   - Additional specialists per `agents/specialist-pool.md` mapping
   - All dispatched reviewers/modes must APPROVE. Any REJECT → return findings → worker fix → re-review
   - 3rd-round same finding → pivot-check trips → status=pivot-needed → STOP
8. **VERIFY GATE** — phase checklist (project-specific, parsed from spec or `CLAUDE.md`):
   - `pnpm test && pnpm lint && pnpm typecheck && pnpm build` for Next.js
   - `pytest && ruff check && mypy` for Python
   - Custom from spec verify section
9. **COMMIT** atomic per worker, with trailers:
   ```
   auto-pilot-iter: {N}
   auto-pilot-phase: {phase}
   auto-pilot-contract: {contract-id}
   ```
   Push, advance phase counter.
10. **REPEAT** until spec's last phase verify passes or hard stop fires

At phase end the PM MAY dispatch the `retro` agent (`agents/retro.md`) — appends evidence-cited doom-loop/wasted-pattern lessons to the project's `.claude/insights.md`; no verdicts, never blocks the loop.

### Hard stops

- Spec's final phase verify all green → SUCCESS report, exit
- Same finding repeats 3 rounds → "strategy pivot needed" report, exit (deny-list whack-a-mole detector)
- Worker timeout >20min → kill, report, exit
- User says "stop autopilot" / Ctrl-C

## How to invoke

```
/auto-pilot start                        # use newest spec in docs/specs/
/auto-pilot start --spec PATH            # explicit spec
/auto-pilot start --max-workers 6        # cap parallelism (default 10)
/auto-pilot start --time-box 8h          # auto-stop after
/auto-pilot status                       # print state.json summary
/auto-pilot resume                       # continue from last checkpoint
/auto-pilot stop                         # mark state.json stopped
/auto-pilot eval [--tier smoke|full] [--case ID] [--repeats N]   # advisory evals harness (see ## eval)
/auto-pilot handoff                      # write next-session handoff (see ## handoff)
```

> The former `commands/auto-pilot.md` router was folded into this skill 2026-06-07 — commands and skills now share one registry namespace, so the same-name pair double-registered. This SKILL.md is the single `/auto-pilot` entry.

## Pre-flight (run before dispatching anything)

1. Confirm repo is git-clean OR `--allow-dirty`
2. Confirm spec exists (newest `docs/specs/*-*.md` OR `--spec` arg OR `SPEC.md`)
3. Confirm `codex` CLI on PATH (for adversarial reviewer)
4. Confirm `.planning/auto-pilot/` exists (create if missing)
5. Print initial scorecard: phase, contracts, est. parallel workers
6. Confirm `git --version` ≥ 2.32 (required for `git commit --trailer` used in worktree apply_to_main amend step):
   ```bash
   v=$(git --version | awk '{print $3}')
   IFS=. read -r maj min _ <<< "$v"
   if ! { [ "$maj" -gt 2 ] || { [ "$maj" -eq 2 ] && [ "$min" -ge 32 ]; }; }; then
     echo "auto-pilot: git $v < 2.32 — required for commit --trailer" >&2; exit 2
   fi
   ```
7. **Subagent discovery probe** (presence health-check — hardened pair is required):
   ```bash
   # `claude --list-agents` does not exist; probe via no-op dispatch with sentinel token.
   probe_result=$(timeout 30 claude -p --max-turns 1 \
      "@subagent:auto-pilot-claude-reviewer reply with literal token AUTOPILOT_PROBE_OK" 2>&1)
   if ! echo "$probe_result" | grep -q AUTOPILOT_PROBE_OK; then
     echo "auto-pilot: subagent discovery probe failed; hardened reviewer pair unavailable — aborting (no legacy fallback)" >&2
     exit 3
   fi
   ```
8. **Codex sandbox probe**:
   ```bash
   if codex exec --sandbox read-only --json --prompt "ping" 2>&1 | grep -qi 'unknown\|invalid'; then
     echo "auto-pilot: codex does not support --sandbox read-only; layer 4 deterrent disabled" >&2
     export AUTO_PILOT_CODEX_SANDBOX_AVAILABLE=0
   else
     export AUTO_PILOT_CODEX_SANDBOX_AVAILABLE=1
   fi
   ```

The hardened pair (`auto-pilot-codex-reviewer` / `auto-pilot-claude-reviewer`) is the only reviewer dispatch path — there is no legacy `general-purpose` inline-text fallback (legacy pair deleted 2026-06-07). All four sandbox layers stay active: frontmatter `tools:` whitelist (layer 1), the env-keyed `pre-reviewer-write.sh` hook (layers 2+3), and the codex `--sandbox read-only` deterrent (layer 4).

## eval

> Folded from the retired `commands/eval-run.md` (2026-06-07); methodology verbatim — harness, flags, and paths unchanged.

Run the cut-1 evals harness (advisory). It clones the repo per case, runs auto-pilot headless on the case spec, asserts the deliverable with a deterministic oracle, and prints an advisory pass-rate vs the blessed baseline. **Never blocks** (cut-1): always exits 0.

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/evals/cli.py run --tier smoke --repeats 1
```

Methodology (`scripts/evals/cli.py` → `scripts/evals/runner.py`):

1. **Select cases** — `--case ID` for one case, else `select_cases(evals/cases, tier)` for the tier (`smoke` default | `full`).
2. **Per attempt, isolate via a fresh local clone** (`git clone --local`), then run auto-pilot headless inside it: `python3 scripts/orchestrator.py init --spec evals/cases/<ID>/spec.md --force --max-workers 2` then `python3 scripts/headless-loop.py --max-iter 20 --max-cost-usd 5.0 --max-concurrent-claude 10000` (large concurrency cap disables the fork-bomb `pgrep claude` guard for the sequential eval loop; non-zero loop exit is expected — the oracle decides pass/fail). Clone teardown is in a `finally`.
3. **Oracle** — `load_case_oracle(ID)` asserts the deliverable deterministically; outcome buckets are pass / fail / error.
4. **Repeat** `--repeats N` (CLI default 5; the slash default above passes 1), `summarize()` per case, and `compare()` vs `evals/baseline.json` (advisory — reports `armed` / `would_fire` / `error_spike`, never blocks). Results written to `evals/results/local.json`.
5. **Cost ceiling** — `--max-total-cost-usd` (default 50.0); stops before the next case once exceeded.

Paths are repo-root-relative: harness driver `scripts/evals/cli.py`, runner `scripts/evals/runner.py`; cases + baseline live at `evals/cases/` and `evals/baseline.json`.

## Built-in friction guards (from /insights analysis)

| Friction class | Guard |
|---|---|
| Path typos (Valut/, /tmp, missing vault) | `hooks/preflight-path.sh` runs SessionStart + before any vault write |
| ruff --fix on composition root | `hooks/pre-edit-composition-root.sh` blocks edits to `**/__init__.py` and re-export modules unless `--force-composition-root` set |
| HTTP-first debug (Naver private bug class) | PM prompt mandates source-read before any external probe |
| Adversarial reviewers writing/git-stashing | Reviewer agents are READ-ONLY (no Edit/Write/Bash-git tools) |
| Wrong verdict slipping through (B4/B5) | Dual review required; either rejection blocks merge |
| SSL stacking outages | Infra changes serialized 1-at-a-time with verify between |
| Interactive TUI in non-interactive shell | PM avoids `claude doctor` etc., uses flag equivalents |
| Over-scoped contracts ("P1.1 not real issue") | `tech-critic-lead` gate BEFORE worker dispatch |
| Implementation without tests | `review-gatekeeper` mode `tdd-gate` rejects runtime change diffs missing matching test file |
| Workers touching files outside their contract | `auto-pilot-claude-reviewer` + `auto-pilot-codex-reviewer` scope-drift check (auto-REJECT on out-of-scope edits) |
| Phase fails leaving partial commits | `scripts/headless-loop.py` snapshots HEAD pre-phase; on `status=failed` it calls `stash_if_dirty` (non-destructive stash with a recoverable label) — `$ROOT` is intentionally not reset hard so worktree cleanup is the recovery unit (`iter.fail_no_root_reset` event logged) |

## Parallel execution backend

The plugin's swarm subsystem is an alternative execution backend: a persistent tmux multi-worker pool (1 PM pane + 4-10 worker panes, each on its own git worktree, file-based ticket bus under `.planning/autopilot/`). Entry points: `/auto-pilot:swarm <init|start|status|stop|ticket|bench>` (bench absorbed swarm-bench 2026-06-07). Scripts live at `${CLAUDE_PLUGIN_ROOT}/swarm/`.

When to prefer which:
- **In-session subagents (this skill's default)** — spec-driven phased work in ONE session; PM context carries between phases; review fan-out + verify gates happen inline; ends when the spec ends.
- **Swarm** — long-running or open-ended goals that should outlive this session, mixed Claude+Codex worker pools, or when you want workers surviving session restarts and observable in tmux. Swarm schedules by ticket scores/ledger, not by spec phases.

## handoff (세션 인수인계)

Triggers: `/auto-pilot handoff`, "핸드오프", "세션 넘겨", "다음 세션 준비" — or the `hooks/context-watch.sh` advisory (context budget running low) recommends this command.

**Path (fixed):** `<repo_root>/.planning/auto-pilot/handoff-next.md`

**Format** — YAML frontmatter + 5 sections, in this order:

```markdown
---
written_at: 2026-06-07T04:00:00Z   # ISO-8601 UTC
session_id: <session id, or "unknown">
head_sha: <git rev-parse HEAD>
status: pending                     # pending | consumed (pickup hook flips it)
---
## ① 상태
What shipped this session; what is mid-flight (branch, uncommitted work).
## ② 결정
Decisions made this session + why (one line each).
## ③ 다음 단계
Ordered next steps.
## ④ NEXT-PROMPT
Verbatim prompt block the next session should execute first.
## ⑤ 산출물 처분표
From `.planning/auto-pilot/session-artifacts.jsonl`, one row per artifact:
SHIPPED → distill→delete 권고 · ACTIVE → keep · SCRATCH → delete 권고.
```

**Write procedure (PM, this is an LLM task — no script writes this file):**
1. Gather: `git log` since session start, `.planning/auto-pilot/session-artifacts.jsonl`, and the live task list.
2. Write the file with `status: pending` and a fresh `written_at`.
3. If the durable next-session entry point changed, also update the auto-memory `MEMORY.md` pointer line.

**Pickup (automatic):** `hooks/preflight-path.sh` (SessionStart) walks up from CWD for the file. If `status: pending` AND `written_at` < 7 days old, it injects the first 6000 chars as SessionStart `additionalContext` and flips the frontmatter to `status: consumed` + `consumed_at: <ISO>`. Stale (>7d), already-consumed, or malformed files are silently skipped (fail-open).

**Disposition (automatic):** `hooks/pm_final_report.sh` (Stop) appends a `## Session artifacts` section to the PM final report — one line per unique ledger path with a naive classification: path under a `plans/`/`specs/` segment → "distill→delete 후보"; consumed `handoff-next.md` → "삭제 후보"; everything else → "확인 필요". The authoritative SHIPPED/ACTIVE/SCRATCH call stays with the PM in section ⑤.

## Read these references when relevant

- `${CLAUDE_PLUGIN_ROOT}/docs/architecture.md` — loop diagram, agent contracts
- `${CLAUDE_PLUGIN_ROOT}/docs/7-phase-template.md` — fallback when spec has no phases
- `${CLAUDE_PLUGIN_ROOT}/agents/pm-orchestrator.md` — PM rules
- `${CLAUDE_PLUGIN_ROOT}/agents/tech-critic-lead.md` — pre-dispatch scope gate
- `${CLAUDE_PLUGIN_ROOT}/agents/review-gatekeeper.md` — security + test-first specialist modes
- `${CLAUDE_PLUGIN_ROOT}/agents/specialist-pool.md` — which extra reviewers to dispatch when
- `${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py` — state mgmt helper
- `${CLAUDE_PLUGIN_ROOT}/scripts/headless-loop.py` — true infinite headless driver (use via `/auto-pilot-server`)
