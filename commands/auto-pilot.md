---
description: Self-driving development loop. PM (Opus 4.7) + Sonnet 1M workers + dual Codex/Claude adversarial review + phase verify gates. Full auto.
argument-hint: "[start|status|resume|stop] [--spec PATH] [--max-workers N] [--time-box DURATION]"
allowed-tools: Bash, Read, Write, Edit, Agent, Glob, Grep, TaskCreate, TaskList, TaskUpdate
---

# /auto-pilot $ARGUMENTS

Invoke the `auto-pilot` skill. The skill loads `${CLAUDE_PLUGIN_ROOT}/skills/auto-pilot/SKILL.md` and drives the PM-Worker-Reviewer loop.

## Subcommands

- `start` (default) — initialize state, dispatch first phase
- `status` — print `.planning/auto-pilot/state.json` summary
- `resume` — continue from last checkpoint
- `stop` — mark state stopped

## Pre-flight (run before dispatching anything)

1. Confirm repo is git-clean OR `--allow-dirty`
2. Confirm spec exists (newest `docs/specs/*-*.md` OR `--spec` arg OR `SPEC.md`)
3. Confirm `codex` CLI on PATH (for adversarial reviewer)
4. Confirm `.planning/auto-pilot/` exists (create if missing)
5. Print initial scorecard: phase, contracts, est. parallel workers
7. **Subagent discovery probe** (PR3 fallback gate):
   ```bash
   # `claude --list-agents` does not exist; probe via no-op dispatch with sentinel token.
   if [ "${AUTO_PILOT_DISABLE_NEW_REVIEWERS:-0}" != "1" ]; then
     probe_result=$(timeout 30 claude -p --max-turns 1 \
        "@subagent:auto-pilot-claude-reviewer reply with literal token AUTOPILOT_PROBE_OK" 2>&1)
     if echo "$probe_result" | grep -q AUTOPILOT_PROBE_OK; then
       export AUTO_PILOT_USE_NEW_REVIEWERS=1
     else
       echo "auto-pilot: subagent discovery probe failed; falling back to general-purpose dispatch" >&2
       export AUTO_PILOT_USE_NEW_REVIEWERS=0
     fi
   else
     export AUTO_PILOT_USE_NEW_REVIEWERS=0
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

In degraded mode (`AUTO_PILOT_USE_NEW_REVIEWERS=0`), PM dispatches via legacy `subagent_type: general-purpose, model: opus`. Hook `pre-reviewer-write.sh` still fires (env-keyed), so layers 2+3 remain active. Layer 1 (frontmatter `tools:` whitelist) disabled.

## Execution

Read `${CLAUDE_PLUGIN_ROOT}/scripts/orchestrator.py` for the canonical loop. Drive it from the main session — do NOT delegate the PM role to a subagent (Opus 4.7 main session IS the PM).

For each phase:
1. Plan contracts (Read spec + current code)
2. Dispatch workers (1 message, N parallel `Agent` blocks with `subagent_type: "general-purpose"` and the model override `sonnet` — Sonnet 4.6 1M context)
3. Dispatch reviewers (1 message, 2 parallel blocks per worker: codex-adversarial + claude-reviewer)
4. Apply approved fixes, commit atomically, advance state

Stop conditions defined in `SKILL.md`.

## Friction guards (auto-loaded via plugin hooks)

`hooks/preflight-path.sh`, `hooks/pre-edit-composition-root.sh`, `hooks/post-deploy-verify.sh` register via `hooks/hooks.json` and fire automatically.
