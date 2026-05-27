---
name: auto-pilot
description: Self-driving development loop. Triggers on /auto-pilot, "auto pilot", "자율 주행", "자율 루프", "자동 개발", "self-driving", "autonomous build", "PM 워커 루프", or when user wants the PM (Opus 4.7) to dispatch Sonnet 4.6 (1M context) workers in parallel, run Codex+Claude dual adversarial review on every diff, execute phase verify gates (test/lint/typecheck/build), and advance through a spec's phases automatically until done. Full auto by default — no confirms. Stops on spec completion, time-box, or hard failure. Built from /insights friction analysis: bakes in path preflight, composition-root guard, code-first debug rule, read-only adversarial constraint, dual-review verdict catching.
---

# auto-pilot

## When this skill fires

User invokes `/auto-pilot start` (or aliases: "자율 주행 시작", "autopilot go", "self-drive this", "PM 루프 돌려") AND a target spec exists at one of:
- `docs/specs/*-*.md` (newest by date)
- `SPEC.md` at repo root
- Path passed as `--spec <path>` arg

## What this skill does

Runs `scripts/orchestrator.py` which executes the PM-Worker-Reviewer loop. The PM stays in the main session (Opus 4.7) and dispatches all subagents via the `Agent` tool.

### Loop (per phase)

1. **READ** state from `.planning/auto-pilot/state.json` + spec + `CLAUDE.md` chain
2. **PLAN** non-overlapping work contracts for current phase (1 contract per parallel worker, max 10)
3. **PREFLIGHT** path validation hook fires (kills typo-path failure class)
4. **DISPATCH** N Sonnet-4.6-1M workers in 1 message (N parallel Agent blocks)
5. **DUAL REVIEW** — fan out 2 reviewers per worker diff in parallel:
   - Codex adversarial (`codex exec -m gpt-5.5-high`)
   - Claude Opus 4.7 cold (fresh subagent, no session context)
   - Both must return APPROVE. Either rejects → return finding to worker → fix → re-review
6. **VERIFY GATE** — phase checklist (project-specific, parsed from spec or CLAUDE.md):
   - `pnpm test && pnpm lint && pnpm typecheck && pnpm build` for Next.js
   - `pytest && ruff check && mypy` for Python
   - Custom from spec verify section
7. **COMMIT** atomic per worker, push, advance phase counter
8. **REPEAT** until spec's last phase verify passes or hard stop fires

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

## Read these references when relevant

- `${CLAUDE_PLUGIN_ROOT}/docs/architecture.md` — loop diagram, agent contracts
- `${CLAUDE_PLUGIN_ROOT}/agents/pm-orchestrator.md` — PM rules
- `${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py` — driver entry
