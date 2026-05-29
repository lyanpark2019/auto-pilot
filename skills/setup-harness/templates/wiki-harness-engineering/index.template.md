---
type: harness-engineering-index
generated: {{DATE}}
sources:
  - notebook-3c01cb29 (Claude Code & Codex)
  - notebook-5b5fb594 (Harness Engineering)
  - skill-improve-codebase-architecture
  - codex-supervisor-session-{{DATE}}
---

# Harness Engineering — {{PROJECT_NAME}}

> Single entry point for the harness engineering knowledge base. Built {{DATE}} by an Opus 4.7 PM supervising five Codex 5.5 xhigh workers via codex exec + file message bus.

## What is "Harness Engineering"

> "The practice of configuring the environment, rules, and tools around a coding agent to improve its reliability." — HumanLayer (coined term), echoed by OpenAI ([[principles/01-doctrine]]).

| Discipline | Layer | Fails when |
|------------|-------|-----------|
| Prompt engineering | Language | Multi-turn autonomous tasks |
| Context engineering | Information | Agent needs behavioural governance, not knowledge |
| **Harness engineering** | **Autonomy** | Acts as the operating envelope — permissions, constraints, mechanical back-pressure |

## How {{PROJECT_NAME}} uses harness engineering

| Surface | Role | File |
|---------|------|------|
| Root `CLAUDE.md` | Progressive-disclosure ToC ([[principles/01-doctrine#P7]]) | `CLAUDE.md` |
| `<scope>/CLAUDE.md` | Per-folder stubs → vault wiki | `<scope>/CLAUDE.md` |
| `docs/rules/` | Forbidden actions, deployment safety, verification methodology | (fill in) |
| `docs/runbooks/` | Incident response | (fill in) |
| Architecture tests | Mechanical back-pressure on import direction ([[principles/01-doctrine#P10]]) | (fill in) |
| Pre-commit guards | (fill in) | (fill in) |

## Tree

```
wiki/harness-engineering/
├── index.md                       (this file)
├── principles/
│   ├── 01-doctrine.md             P1..P15 + 12 sources
│   ├── 02-supervisor-pattern.md   Opus PM + Codex×N
│   └── 03-message-bus.md          .planning/harness-rewrite ticket/outbox/done
├── layers/
│   ├── interface.md
│   ├── application.md
│   ├── domain.md
│   ├── infrastructure.md
│   └── cross-cutting.md
├── deepening-backlog.md           N candidates ranked
├── friction-map.md                cross-layer top-N issues
└── runbooks/                      (absorbed from project's existing runbooks)
```

## Reading order

1. New to the codebase → [[principles/01-doctrine]] → [[principles/02-supervisor-pattern]]
2. Touching code → relevant `layers/{your-layer}.md`
3. Considering a refactor → [[deepening-backlog]] + [[friction-map]]
4. Operating in production → `runbooks/` pages

## Provenance

Built via the supervisor pattern in `principles/02-supervisor-pattern.md`. Source ledger: `.planning/harness-rewrite/ledger.md`. Doctrine reference: `.planning/harness-rewrite/refs/doctrine.md` (mirror of skill's `references/codex-multi-worker-doctrine.md`).
