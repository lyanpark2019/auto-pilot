# Plan Mode + Extended Thinking for harness setup

Two related Claude Code features that reduce harness-installation cost and improve decision quality.

## Plan Mode (read-only planning)

Toggled via `/` command menu or `permissionMode: plan` in subagent frontmatter.

**Token savings**: 40–60% per session (Anthropic Code with Claude 2026). Plan Mode disables file writes and bash execution; Claude can only read. Forces a thinking-first → execution-second workflow.

**When to use for harness work**:

| Harness task | Plan Mode? | Why |
|--------------|-----------|-----|
| Audit existing harness | ✅ | Read-only by nature |
| Score (harness script direct) | ✅ | Pure read |
| Drift scan | ✅ | Reads files + greps |
| Bootstrap new harness | ❌ | Needs writes |
| Run autonomous loop | ❌ | Loop applies autofixes |
| Plan a multi-agent build | ✅ first, then ❌ | Plan in plan mode → exit → execute |

### Recommended workflow for harness setup

```
1. /plan-mode on
2. bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/score-harness.sh   # see current state, read-only
3. Discuss with Claude: which dimensions matter most, what to skip
4. /plan-mode off
5. TARGET=95 MAX_ITERATIONS=15 bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/harness-loop.sh
```

## Extended Thinking budget

The thinking-budget keywords (ranked low → high effort):

```
think → think hard → think harder → megathink → ultrathink
```

Or durable per-session via `effort.level`:

| Level | Use for harness |
|-------|----------------|
| `low` | Routine: bootstrap, drift-scan |
| `medium` | Default: score, verify |
| `high` | Plan Mode discussions on which dimensions to improve |
| `xhigh` | Architectural decisions: which subagent pattern fits |
| `max` | Designing custom hook patterns for a novel constraint |

`effort.level` is passed into hook stdin — hooks can branch on thinking depth. Example: gate expensive operations to `medium+`.

```bash
# In hook script
effort_level=$(jq -r '.effort.level // "medium"' <<< "$input")
case "$effort_level" in
  low) skip_extra_checks=1 ;;
  *) skip_extra_checks=0 ;;
esac
```

## Historical: 3-agent harness pattern (deleted 2026-06-07)

The Anthropic harness-design paper (Mar 2026) described a planner/generator/evaluator trio. The corresponding agents (`harness-planner`, `harness-generator`, `harness-evaluator`) were removed as 1:1 duplicates of the auto-pilot loop — use `/auto-pilot` instead. Cost calibration from the paper applied the same effort-level reasoning (higher on planning, medium on generation/QA).

## Anti-patterns

- ❌ Using `ultrathink` for every step — burns tokens with no quality gain on routine work
- ❌ Using Plan Mode for execution — file writes are disabled; will fail silently
- ❌ Mixing `low` effort with destructive operations — false economy

## Hook gating example

`session-start.sh` can branch on effort:

```bash
effort=$(jq -r '.effort.level // "medium"' <<< "$input")
if [ "$effort" = "low" ]; then
  # Minimal context — just branch + HEAD
  ctx="branch: $(git branch --show-current), HEAD: $(git rev-parse --short HEAD)"
else
  # Full context
  ctx=$(...verbose...)
fi
```

This makes the harness adaptive to the user's chosen budget.
