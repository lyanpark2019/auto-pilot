---
name: specialist-pool
description: Registry of optional specialist reviewers PM can dispatch in addition to the default auto-pilot-codex-reviewer + auto-pilot-claude-reviewer pair. PM picks specialists per contract based on changed file patterns. Specialists are read-only, parallel-dispatched, and report APPROVE/REJECT + findings. This file is not a runnable agent itself — it's the lookup table.
model: opus
---

# Specialist reviewer pool

The PM's default review fan-out is:
1. `auto-pilot-codex-reviewer` (always)
2. `auto-pilot-claude-reviewer` (always)
3. `review-gatekeeper` mode `tdd-gate` (if diff touches runtime code)

In addition, PM scans the diff's file paths and dispatches matching specialists from this pool **in the same parallel message** as the default reviewers.

## Pattern → specialist mapping

| File pattern in diff | Specialist agent | Mode | Reason |
|---|---|---|---|
| `app/api/**`, `app/**/route.*`, `**/middleware.*`, `lib/auth*`, `lib/session*`, `*supabase*`, `*insforge*`, `.env*`, `config*`, SQL/migration files, `*payment*`, `*stripe*`, `*webhook*`, `*upload*`, `*storage*`, `*signed-url*` | `review-gatekeeper` | `security` | Trust boundary — OWASP Top 10 gate |
| Any worker diff touching application (runtime) code (not docs/config-only) | `review-gatekeeper` | `tdd-gate` | Test-first hard gate — runtime diff missing a matching test → REJECT, delete impl, restart from a failing test |
| `**/*migration*.sql`, `**/migrations/**`, `prisma/schema.prisma`, `**/*.sql` | `database-reviewer` (Phase 2+ — port from everything-claude-code/agents/database-reviewer.md when needed) | — | Schema correctness, RLS, index plan |
| `**/*.tf`, `**/*Dockerfile*`, `**/k8s/**`, `**/.github/workflows/**`, `vercel.json`, `vercel.ts`, `**/fly.toml` | `infra-reviewer` (TBD) | — | Infra change blast radius |
| `prompts/**`, `**/*.prompt.md`, anywhere with LLM call + prompt template | `prompt-reviewer` (TBD) | — | Prompt drift, cost regression |
| Tests-only diffs (only `tests/**`, `**/*.test.*`) | `test-quality-reviewer` (TBD) | — | Are tests real or theatre? |

`review-gatekeeper` carries both gates (modes `security` + `tdd-gate`) in one agent. A diff may match both rows → PM dispatches the agent once per mode (or instructs it to run both modes), and each mode emits its own verdict.

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

If 2 specialists disagree (e.g., `review-gatekeeper` (`security`) says REJECT but `auto-pilot-claude-reviewer` says APPROVE), PM treats it as REJECT — the conservative path. PM logs the disagreement in `.planning/auto-pilot/reviewer-disagreements-phase-N.jsonl` for later root-cause analysis.

## Tier system

- **Tier 1 (ship now)**: `auto-pilot-codex-reviewer`, `auto-pilot-claude-reviewer`, `review-gatekeeper` (modes `security` + `tdd-gate`). These exist in `auto-pilot/agents/`.
- **Tier 2 (port on demand)**: `database-reviewer`, `infra-reviewer`, `prompt-reviewer`, `test-quality-reviewer`. PM will request port from `~/Documents/Project/everything-claude-code/agents/` when first triggered.

## Don't over-dispatch

If a diff touches 1 file, don't dispatch 5 specialists. Cap at default 3 + max 2 specialists per contract. Specialists exist to catch class-specific issues, not to add noise.
