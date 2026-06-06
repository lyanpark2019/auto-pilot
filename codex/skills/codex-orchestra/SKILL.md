---
name: codex-orchestra
description: Use when the user invokes $codex-orchestra, /codex-orchestra, "codex orchestra", or asks to run Opus/Claude as PM with Codex as the implementation worker/subagent. Coordinates a plan to Codex implement to Opus review/gate loop from Codex, without letting Claude write source or test files.
---

# Codex Orchestra

## Overview

Codex-side conductor mode. In Claude Code, `/codex-orchestra` is a Claude skill.
In Codex, this skill provides the sibling workflow: **Opus/Claude is PM and
review gate; Codex is the implementation worker**.

This is not a Claude slash command. It triggers in Codex through this skill's
description when the user says `$codex-orchestra`, `/codex-orchestra`,
`codex orchestra`, or asks for Opus PM + Codex worker.

## Role Split

- **Opus PM via Claude CLI** plans, reviews, gates, and decides revision scope.
- **Codex** reads, implements source/test code, runs verification, and reports
  evidence.
- Claude/Opus must run in plan/review mode only. Do not let Claude write source
  or test files for this workflow.
- Codex may write code only after the user approves the PM plan.
- No commits, pushes, hook bypasses, or bulk staging unless the user explicitly
  asks.

## Preflight

Before a repo task:

1. Read local instructions (`AGENTS.md`, `CLAUDE.md`, nearest nested files).
2. Run `git status --short` and preserve unrelated work.
3. Confirm Claude CLI is available:

```bash
claude --help
```

4. If Claude CLI/auth/model access fails, stop and report. Do not pretend Opus
   reviewed the work.

## Phase 1: Opus PM Plan

Collect enough repo context with read-only commands. Then ask Opus for a PM plan:

```bash
claude -p --model opus --permission-mode plan --output-format json \
  --append-system-prompt 'You are the PM/reviewer/gate for a Codex worker. Do not edit files. Produce a concise plan, scope boundaries, acceptance checks, and risks. Claude writes no implementation source or tests.' \
  '<task and repo context>'
```

Require the PM response to include:

- `Plan`
- `Scope`
- `Non-goals`
- `Acceptance Checks`
- `Verification Commands`
- `Risks`
- `Codex Handoff`

Show the plan to the user and pause for approval before coding.

## Phase 2: Codex Implements

Codex implements the approved handoff directly in the repo. Keep changes narrow:

- Touch only files in the approved scope.
- Prefer existing patterns and public test seams.
- Run the PM's verification commands.
- Do not stage or commit.

Final worker output to the user must include:

- `Summary`
- `Validation`
- `Remaining Risks`
- `Files Changed`

## Phase 3: Opus Review Gate

After implementation and local verification, collect diff evidence:

```bash
git status --short
git diff --stat
git diff -- <approved paths>
```

Ask Opus to review:

```bash
claude -p --model opus --permission-mode plan --output-format json \
  --append-system-prompt 'You are the PM review gate for Codex work. Do not edit files. Review the supplied diff and validation evidence. Return APPROVED, NEEDS_REVISION, or FAILED with concrete findings.' \
  '<approved plan, validation output, git status, diff stat, and relevant diff>'
```

Respect the PM verdict:

- `APPROVED`: report summary, validation, risks, and proposed commit message.
- `NEEDS_REVISION`: apply only the PM-approved revision scope, then review again.
- `FAILED`: stop and report. Do not self-approve.

## Failure Rules

- If Opus output is empty, malformed, over budget, unauthenticated, or not
  clearly a PM verdict, stop and report the exact failure.
- If PM instructions conflict with local repo instructions or the user, follow
  the higher-precedence instruction and report the conflict.
- If a task is small enough that Opus PM would be ceremony, say so and ask before
  using the orchestra workflow anyway.
