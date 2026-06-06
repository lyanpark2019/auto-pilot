---
name: auto-pilot
description: Self-driving development loop. Triggers on /auto-pilot, "auto pilot", "자율 주행", "자율 루프", "자동 개발", "self-driving", "autonomous build", "PM 워커 루프", or when user wants the PM (Opus 4.7) to dispatch Sonnet 4.6 (1M context) workers in parallel, run Codex+Claude dual adversarial review on every diff, execute phase verify gates (test/lint/typecheck/build), and advance through a spec's phases automatically until done. Full auto by default — no confirms. Stops on spec completion, time-box, or hard failure. Built from /insights friction analysis — bakes in path preflight, composition-root guard, code-first debug rule, read-only adversarial constraint, dual-review verdict catching.
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
4. **TECH-CRITIC GATE** (BEFORE worker dispatch) — fan out `tech-critic-lead` over each contract in parallel. "기능은 비용". Reject contracts that fail evidence/value/scope check. Drop or slice rejected ones. Log rejections to `.planning/auto-pilot/critic-rejections-phase-N.jsonl`
5. **PREFLIGHT** path validation hook fires (kills typo-path failure class)
6. **DISPATCH WORKERS** — N Sonnet-4.6-1M workers in 1 message (N parallel Agent blocks, `isolation: worktree`)
7. **REVIEW FAN-OUT** in parallel per worker diff:
   - Default: `codex-adversarial`, `claude-reviewer`
   - If diff touches runtime code: + `tdd-enforcer`
   - If diff touches trust boundary (auth/API/secrets/SQL/migrations/payments): + `security-reviewer`
   - Additional specialists per `agents/specialist-pool.md` mapping
   - All dispatched reviewers must APPROVE. Any REJECT → return findings → worker fix → re-review
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
```

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
| Implementation without tests | `tdd-enforcer` rejects runtime change diffs missing matching test file |
| Workers touching files outside their contract | `claude-reviewer` + `codex-adversarial` scope-drift check (auto-REJECT on out-of-scope edits) |
| Phase fails leaving partial commits | `scripts/headless-loop.py` snapshots HEAD pre-phase; on `status=failed` it calls `stash_if_dirty` (non-destructive stash with a recoverable label) — `$ROOT` is intentionally not reset hard so worktree cleanup is the recovery unit (`iter.fail_no_root_reset` event logged) |

## Parallel execution backend

The plugin's swarm subsystem is an alternative execution backend: a persistent tmux multi-worker pool (1 PM pane + 4-10 worker panes, each on its own git worktree, file-based ticket bus under `.planning/autopilot/`). Entry points: `/auto-pilot:swarm <init|start|status|stop|ticket>`, bench via `swarm-bench`. Scripts live at `${CLAUDE_PLUGIN_ROOT}/swarm/`.

When to prefer which:
- **In-session subagents (this skill's default)** — spec-driven phased work in ONE session; PM context carries between phases; review fan-out + verify gates happen inline; ends when the spec ends.
- **Swarm** — long-running or open-ended goals that should outlive this session, mixed Claude+Codex worker pools, or when you want workers surviving session restarts and observable in tmux. Swarm schedules by ticket scores/ledger, not by spec phases.

## Read these references when relevant

- `${CLAUDE_PLUGIN_ROOT}/docs/architecture.md` — loop diagram, agent contracts
- `${CLAUDE_PLUGIN_ROOT}/docs/7-phase-template.md` — fallback when spec has no phases
- `${CLAUDE_PLUGIN_ROOT}/agents/pm-orchestrator.md` — PM rules
- `${CLAUDE_PLUGIN_ROOT}/agents/tech-critic-lead.md` — pre-dispatch scope gate
- `${CLAUDE_PLUGIN_ROOT}/agents/tdd-enforcer.md` — test-first hard rule
- `${CLAUDE_PLUGIN_ROOT}/agents/specialist-pool.md` — which extra reviewers to dispatch when
- `${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py` — state mgmt helper
- `${CLAUDE_PLUGIN_ROOT}/scripts/headless-loop.py` — true infinite headless driver (use via `/auto-pilot-server`)
