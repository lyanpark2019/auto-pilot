---
name: specialist-pool
description: Registry of optional specialist reviewers PM can dispatch in addition to the default codex-adversarial + claude-reviewer pair. PM picks specialists per contract based on changed file patterns. Specialists are read-only, parallel-dispatched, and report APPROVE/REJECT + findings. This file is not a runnable agent itself — it's the lookup table.
model: opus
---

# Specialist reviewer pool

The PM's default review fan-out is:
1. `codex-adversarial` (always)
2. `claude-reviewer` (always)
3. `tdd-enforcer` (if diff touches runtime code)

In addition, PM scans the diff's file paths and dispatches matching specialists from this pool **in the same parallel message** as the default reviewers.

## Pattern → specialist mapping

| File pattern in diff | Specialist agent | Reason |
|---|---|---|
| `app/api/**`, `app/**/route.*`, `**/middleware.*`, `lib/auth*`, `*supabase*`, `*insforge*`, `.env*`, SQL/migration files, `*payment*`, `*webhook*`, `*upload*`, `*signed-url*` | `security-reviewer` | Trust boundary |
| `**/*migration*.sql`, `**/migrations/**`, `prisma/schema.prisma`, `**/*.sql` | `database-reviewer` (Phase 2+ — port from everything-claude-code/agents/database-reviewer.md when needed) | Schema correctness, RLS, index plan |
| `**/*.tf`, `**/*Dockerfile*`, `**/k8s/**`, `**/.github/workflows/**`, `vercel.json`, `vercel.ts`, `**/fly.toml` | `infra-reviewer` (TBD) | Infra change blast radius |
| `prompts/**`, `**/*.prompt.md`, anywhere with LLM call + prompt template | `prompt-reviewer` (TBD) | Prompt drift, cost regression |
| Tests-only diffs (only `tests/**`, `**/*.test.*`) | `test-quality-reviewer` (TBD) | Are tests real or theatre? |

## Dispatch contract

When PM dispatches a specialist, the prompt template is:

```
You are dispatched as a specialist reviewer for auto-pilot phase {N} contract {K}.
You are READ-ONLY: Read, Grep, Glob, and Bash (only read-only commands + project test runner).
No Edit, no Write, no git mutation, no Agent dispatch.

DIFF:
{worker diff}

CONTRACT SCOPE:
{scope files list}

SPEC SECTION:
{spec excerpt}

PROJECT RULES:
{CLAUDE.md excerpts}

Return your structured YAML verdict per your agent's output format.
```

## How PM gates on specialists

Default reviewers + ALL dispatched specialists must APPROVE for the diff to merge. A single REJECT from any specialist blocks the merge and returns findings to the worker.

If 2 specialists disagree (e.g., security-reviewer says REJECT but claude-reviewer says APPROVE), PM treats it as REJECT — the conservative path. PM logs the disagreement in `.planning/auto-pilot/reviewer-disagreements-phase-N.jsonl` for later root-cause analysis.

## Tier system

- **Tier 1 (ship now)**: `codex-adversarial`, `claude-reviewer`, `tdd-enforcer`, `security-reviewer`. These exist in `auto-pilot/agents/`.
- **Tier 2 (port on demand)**: `database-reviewer`, `infra-reviewer`, `prompt-reviewer`, `test-quality-reviewer`. PM will request port from `~/Documents/Project/everything-claude-code/agents/` when first triggered.

## Don't over-dispatch

If a diff touches 1 file, don't dispatch 5 specialists. Cap at default 3 + max 2 specialists per contract. Specialists exist to catch class-specific issues, not to add noise.
