---
type: harness-pattern
pattern: supervisor
generated: {{DATE}}
validated: {{DATE}}
sources:
  - kylestratis-better-practices
  - claude-code-advanced-course-3h
  - openai-harness-engineering-blog
  - one-million-lines-ai-plus-ep6
---

# Pattern — Opus PM + Codex Worker

> Hierarchical fan-out / fan-in. One supervising model orchestrates N independent worker instances of a different model family.

## When to use

| Use | Skip |
|-----|------|
| Codebase-wide analysis (per-layer or per-module) | Single-file edits |
| Multiple drafts requiring fresh-context QA | Conversational Q&A |
| Long-running deterministic work benefiting from parallelism | Anything fitting one Opus turn |
| Model diversity needed (Codex strength + Opus judgment) | Identical work one Opus session can do faster |

Doctrine: [[01-doctrine#P1]] fan-out, [[01-doctrine#P2]] model diversity, [[01-doctrine#P3]] context firewall.

## Role contract

| Role | Model | Responsibility | Output |
|------|-------|----------------|--------|
| **PM** | main session (interactive Claude Code, operator-selected model) | friction map, ticket dispatch, outbox review, doctrine curation, vault publish gate | `.planning/harness-rewrite/ledger.md`, ticket JSON, merge decisions |
| **Worker × N** | Codex 5.5 xhigh (`codex exec`) | mechanical layer/module analysis, draft authoring, dependency mapping | `.planning/harness-rewrite/outbox/worker-{N}/*.md` |

PM **never** writes worker output. Worker **never** writes PM ledger.

## Mechanism — `codex exec` sync, two dispatch modes

`codex-companion.mjs --background` returns a job ID immediately, but the broker daemon's job-table is process-local; a fresh `codex-companion status` invocation returns `No jobs recorded yet`. State is not round-trippable from the CLI. **Never use it for this pattern.**

Use native `codex exec` (synchronous) in one of two modes. Both write final response stdout → outbox file.

### Mode A — Claude `run_in_background` (one-shot, in-session)

```bash
TICKET="$(cat .planning/harness-rewrite/inbox/worker-N/<ticket>.json)"
{ echo "$PROMPT"; echo "$TICKET"; } | \
  timeout 1200 codex exec \
    --skip-git-repo-check -s read-only --color never \
    -c model="gpt-5.5" -c model_reasoning_effort="xhigh" \
    - > .planning/harness-rewrite/outbox/worker-N/<ticket>.md \
    2> .planning/harness-rewrite/outbox/worker-N/<ticket>.log
```

PM (this Claude session) calls N of these with `run_in_background=true`. Completion notification arrives in the next Claude turn.

### Mode B — tmux pane (long-running, operator-driven)

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/codex-analyze.sh spawn <project_root> 5
# Boots tmux session: pane 0 (PM) + pane 1..5 (worker polling loops via worker-loop.sh).
# PM (operator at pane 0) drops ticket into inbox/worker-N/<ticket>.json.
# Worker pane polls, runs codex exec sync, writes outbox/worker-N/<ticket>.md, moves ticket to done/.
tmux attach -t harness  # to observe
```

Pane survives if the operator detaches. macOS bash 3.2 compatible.

### Mode selection

| Use Mode A when | Use Mode B when |
|-----------------|-----------------|
| One-shot dispatch this session | Long-running or multi-session work |
| Automation pipeline (CI) | Operator wants live pane observation |
| No human at the keyboard | Human-in-loop (P5) round-robin |
| Outside operator workflows | PM Claude session might exit/restart |

Empirical duration: 9–18 min per worker at `--effort xhigh` (~3000 word output, read-only walk). Adjust `timeout` accordingly. Dummy ticket smoke (PONG) = ~35s.

## Layer assignment (calibrate per project)

```
worker-1 → src/interface/
worker-2 → src/application/ + adjacent runtime modules
worker-3 → src/domain/ + data models
worker-4 → src/infrastructure/
worker-5 → src/config/ + src/composition/ + cross-cutting concerns
```

Calibrate to clean-architecture or DDD boundaries of YOUR codebase. {{PROJECT_NAME}} mapping in `.planning/harness-rewrite/ledger.md`.

## Ticket schema

```json
{
  "ticket_id": "<phase>-<worker>",
  "phase": "01-discover | 02-draft | 03-qa",
  "layer": "<one of 5>",
  "scope_files": ["glob1", "glob2"],
  "vocabulary_ref": "Module/Interface/Seam/Depth/Leverage/Locality lens",
  "doctrine_ref": ".planning/harness-rewrite/refs/doctrine.md",
  "deliverable_path": "outbox/worker-N/<ticket_id>.md",
  "format": {"sections": [...], "max_words": 3000, "fact_citation_required": true, "deletion_test": true},
  "codex_invocation": {"model": "gpt-5.5", "effort": "xhigh", "mode": "exec", "tools_allowed": ["read","grep","find"]}
}
```

Every worker output cites `path:line` and passes deletion test ([[01-doctrine#P15]]). PM rejects (reissues) any output that fails either gate.

## Cross-links

- [[01-doctrine]] — full 15 principles
- [[03-message-bus]] — file-bus contract (inbox/outbox/done)
- `.planning/harness-rewrite/ledger.md` — operational ledger
