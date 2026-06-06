---
name: auto-pilot
description: Self-driving development loop. PM (Opus 4.7) + Sonnet 1M workers + dual Codex/Claude adversarial review + phase verify gates. Full auto.
argument-hint: "[start|status|resume|stop|eval|handoff] [--spec PATH] [--max-workers N] [--time-box DURATION]"
allowed-tools: Bash, Read, Write, Edit, Task, Glob, Grep, TaskCreate, TaskList, TaskUpdate
---

# /auto-pilot $ARGUMENTS

Invoke the `auto-pilot` skill. The skill loads `${CLAUDE_PLUGIN_ROOT}/skills/auto-pilot/SKILL.md` and drives the PM-Worker-Reviewer loop.

## Subcommands

- `start` (default) — initialize state, dispatch first phase
- `status` — print `.planning/auto-pilot/state.json` summary
- `resume` — continue from last checkpoint
- `stop` — mark state stopped
- `eval` — run the cut-1 evals harness in advisory mode (see `## eval` below)
- `handoff` — write the next-session handoff document (see `## handoff` below)

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

## Execution

Read `${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py` for the canonical loop. Drive it from the main session — do NOT delegate the PM role to a subagent (Opus 4.7 main session IS the PM).

For each phase:
1. Plan contracts (Read spec + current code)
2. Dispatch workers (1 message, N parallel `Agent` blocks with `subagent_type: "general-purpose"` and the model override `sonnet` — Sonnet 4.6 1M context)
3. Dispatch reviewers (1 message, 2 parallel blocks per worker). The hardened pair is the only path: `auto-pilot-codex-reviewer` + `auto-pilot-claude-reviewer` (ticket-JSON contract, frozen-diff SHA, sandboxed; defined in `agents/auto-pilot-{codex,claude}-reviewer.md`). The subagent discovery probe (step 7 above) is a presence health-check; if it fails the loop aborts rather than degrading to an inline-text reviewer.
4. Apply approved fixes, commit atomically, advance state

Stop conditions defined in `SKILL.md`.

## eval

> Folded from the retired `commands/eval-run.md` (2026-06-07). The slash entry is now `/auto-pilot eval ...`; methodology is verbatim — the harness, flags, and paths are unchanged.

Run the cut-1 evals harness (advisory). It clones the repo per case, runs auto-pilot headless on the case spec, asserts the deliverable with a deterministic oracle, and prints an advisory pass-rate vs the blessed baseline. **Never blocks** (cut-1): always exits 0.

Usage: `/auto-pilot eval [--tier smoke|full] [--case ID] [--repeats N]`

Invocation (allowed-tool: `Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/evals/cli.py:*)`):

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

## handoff

Also triggers on: "핸드오프", "세션 넘겨", "다음 세션 준비", or the `context-watch.sh` hook advisory recommending it. Full format spec: `SKILL.md ## handoff (세션 인수인계)`.

You (the PM) write `<repo_root>/.planning/auto-pilot/handoff-next.md` — this is an LLM authoring task, not a script:

1. **Gather** — `git log --oneline <session-start-sha>..HEAD` (what shipped), `.planning/auto-pilot/session-artifacts.jsonl` (artifact ledger), and the live task list (mid-flight work).
2. **Write** the file: YAML frontmatter (`written_at` ISO-8601 UTC, `session_id`, `head_sha` = current HEAD, `status: pending`) + sections ① 상태 (shipped / mid-flight) ② 결정 (decisions + why, this session) ③ 다음 단계 (ordered) ④ NEXT-PROMPT (verbatim block the next session executes first) ⑤ 산출물 처분표 (per ledger path: SHIPPED → distill→delete 권고 / ACTIVE → keep / SCRATCH → delete 권고).
3. **Memory pointer** — if the durable next-session entry point changed, update the auto-memory `MEMORY.md` pointer line to reference the handoff.

Next session, `hooks/preflight-path.sh` (SessionStart) auto-injects a pending fresh (<7d) handoff as `additionalContext` and flips it to `status: consumed`; `hooks/pm_final_report.sh` (Stop) appends a naive `## Session artifacts` disposition table to the PM final report.

## Friction guards (auto-loaded via plugin hooks)

`hooks/preflight-path.sh`, `hooks/pre-edit-composition-root.sh`, `hooks/post-deploy-verify.sh` register via `hooks/hooks.json` and fire automatically.
