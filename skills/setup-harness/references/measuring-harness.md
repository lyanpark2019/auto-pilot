# Measuring harness effectiveness

You can't improve what you can't measure. Anthropic's harness research used wall-clock + cost; the broader community converges on these metrics.

## Quantitative metrics (track weekly)

| Metric | What it captures | Tool |
|--------|-----------------|------|
| PRs merged / day | Agent throughput | GitHub API |
| Rework rate | % of PRs reopened or revised after merge | gh + custom script |
| Review-comment count / PR | Mean human comments before approve | gh api |
| Hook violation rate | hooks blocked per session | `.claude/logs/tool-use.log` |
| Time-to-first-test-pass | from prompt to all-green | wall clock + git log |
| Token spend / feature | Anthropic billing API | API |
| Test coverage delta | +/- coverage per PR | coverage.xml / lcov |
| Agent-induced regressions | bugs whose blame is an agent commit | `git blame` + bug tracker |

## Effectiveness baseline

Before harness, measure for 2 weeks. After harness MVH (Week 1), measure for 2 weeks. Compare deltas. Morph's data:

- Same model, different harness: **+22 points** SWE-bench
- Same harness, different model: **+1 point** SWE-bench

If your delta is <5pt on equivalent benchmark, the harness isn't doing its job.

## Token-cost guardrails

Anthropic's GAN-style harness: $9 solo → $200 multi-agent (20x). Set a per-session budget:

```bash
# .claude/scripts/budget-guard.sh — PreToolUse, soft warn at 50% / hard block at 100%
SPENT="$(curl -s https://api.anthropic.com/v1/usage ... | jq -r '.daily_cost')"
LIMIT="${HARNESS_DAILY_BUDGET_USD:-50}"
if (( $(echo "$SPENT > $LIMIT" | bc -l) )); then
  echo "BLOCKED: daily budget exceeded ($SPENT / $LIMIT). Resume tomorrow." >&2
  exit 2
fi
```

## When to strip harness components

Anthropic principle: "every component encodes an assumption about what the model can't do — stress test as models improve."

Quarterly review checklist:

- [ ] Disable each hook for one day; check if quality regresses. If not, the hook is no longer load-bearing.
- [ ] Compare current model on a held-out task with and without the multi-agent harness. If the gap closed, remove the harness layer.
- [ ] Re-run linter rule set against last 90 days of merged PRs. Rules with zero firings in 90 days → review for removal.
- [ ] Recount CLAUDE.md lines. Drift toward verbosity is gradual; cut anything inferable from code.

## Telemetry hook (PostToolUse, non-blocking)

```bash
#!/usr/bin/env bash
input="$(cat)"
ts=$(date -Iseconds)
event=$(jq -r '.hook_event_name // "?"' <<< "$input")
tool=$(jq -r '.tool_name // "?"' <<< "$input")
duration=$(jq -r '.tool_response.duration_ms // 0' <<< "$input")
mkdir -p "${CLAUDE_PROJECT_DIR}/.claude/logs"
echo "$ts $event $tool ${duration}ms" >> "${CLAUDE_PROJECT_DIR}/.claude/logs/tool-use.log"
```

Aggregate weekly:

```bash
awk '{print $3}' .claude/logs/tool-use.log | sort | uniq -c | sort -rn
```

## Anti-metrics (don't optimize for)

- **Lines of code written** — agents will inflate
- **Commits / day** — gets inflated by trivial commits
- **Test count** — agents add throwaway tests to satisfy gate; check coverage on critical paths instead
- **CLAUDE.md length** — bigger ≠ better; track compliance rate, not size
