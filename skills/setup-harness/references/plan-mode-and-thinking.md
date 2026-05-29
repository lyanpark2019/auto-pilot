# Plan Mode + Extended Thinking for harness setup

Two related Claude Code features that reduce harness-installation cost and improve decision quality.

## Plan Mode (read-only planning)

Toggled via `/` command menu or `permissionMode: plan` in subagent frontmatter.

**Token savings**: 40–60% per session (Anthropic Code with Claude 2026). Plan Mode disables file writes and bash execution; Claude can only read. Forces a thinking-first → execution-second workflow.

**When to use for harness work**:

| Harness task | Plan Mode? | Why |
|--------------|-----------|-----|
| Audit existing harness | ✅ | Read-only by nature |
| Score (`harness-score`) | ✅ | Pure read |
| Drift scan | ✅ | Reads files + greps |
| Bootstrap new harness | ❌ | Needs writes |
| Run autonomous loop | ❌ | Loop applies autofixes |
| Plan a multi-agent build | ✅ first, then ❌ | Plan in plan mode → exit → execute |

### Recommended workflow for harness setup

```
1. /plan-mode on
2. /harness-score        # see current state, read-only
3. Discuss with Claude: which dimensions matter most, what to skip
4. /plan-mode off
5. /harness-loop 95 15   # execute the plan
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

## Combining with the 3-agent harness

The Anthropic harness-design paper (Mar 2026) used:

| Subagent | Effort level | Plan Mode |
|----------|--------------|-----------|
| `harness-planner` | `xhigh` or `max` | not used (writes spec.md) |
| `harness-generator` | `high` | not used (writes code) |
| `harness-evaluator` | `medium` | optional first pass for contract review |

Higher effort on the Planner is justified — its spec quality compounds into every downstream sprint. Cheaper effort on the Evaluator is fine because criteria are hard-coded.

## Cost impact

Anthropic's harness-design DAW example:

```
Planner    4.7 min  $0.46    (effort: high)
Build×3    3h 19m   $113.85  (effort: medium)
QA×3      25.2 min  $10.39   (effort: medium)
Total     3h 50m    $124.70
```

Switching Planner to `low` effort would cut $0.46 → ~$0.10 but spec quality drops; the savings are not worth it. Switching QA to `xhigh` would cost ~$30 more with marginal quality gain. The defaults above reflect this calibration.

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
