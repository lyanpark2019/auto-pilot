---
name: to-issues
description: Break a plan, spec, PRD, or conversation into independently grabbable GitHub or local issues. Use when the user wants implementation work sliced into vertical issue tickets.
---

# To Issues


Use this skill to turn a plan into issue tickets that separate work by independently shippable vertical slices.

## Codex Coordination

- Obey the active collaboration mode. In Plan Mode, inspect and propose only; do not mutate files, issues, branches, or external systems.
- Read local `AGENTS.md`, `CLAUDE.md`, and nested instructions before repository writes.
- Preserve unrelated dirty work. Never bulk-stage, bypass hooks, or run destructive commands without explicit approval.
- If another active skill gives stricter verification or safety rules, follow the stricter rule.

Creating remote issues requires an explicit user request and a verified tracker command. Without that request, output markdown drafts only.

## Output Contract

Always return two layers, even when not publishing:

1. **Proposed breakdown**: numbered slices with Title, Type (`HITL` or `AFK`), Blocked by, and User stories covered. Include the quiz prompts the user should answer before publishing.
2. **Issue drafts**: each draft uses the upstream template headings `## Parent` when applicable, `## What to build`, `## Acceptance criteria`, and `## Blocked by`, plus test plan, labels, and explicit non-goals when useful.

Finish with a coverage check mapping source requirements to issues.


## Source Fidelity Notes

Break plans into tracer bullet issues: thin vertical slices through all integration layers, not horizontal layer tickets.

The issue tracker and triage label vocabulary should already be configured by `$setup-matt-pocock-skills`.

Slices may be HITL or AFK. HITL slices need human interaction such as architecture or design review; AFK slices can be implemented and merged without human interaction.

Quiz the user on the numbered breakdown before publishing. Ask: Does the granularity feel right? Are dependency relationships correct? Should slices merge or split? Are HITL and AFK labels correct?

Every issue body must include Blocked by. Publish blockers first when creating real issues. Do NOT close or modify any parent issue.
## Workflow

1. Read the source plan/spec.
   - Identify goals, constraints, public interfaces, tests, rollout, and non-goals.
   - If the source is ambiguous, ask only questions that change issue boundaries.

2. Slice vertically.
   - Each issue should produce user-visible or system-observable value.
   - Avoid horizontal tickets like "add models", "add UI", "write tests" unless that is truly independent.

3. Write each issue.
   - Title: action plus outcome.
   - Include `## What to build` with end-to-end behavior, not layer-by-layer implementation.
   - Include `## Acceptance criteria` with independently verifiable checklist items.
   - Include `## Blocked by` with a real dependency or `None - can start immediately`.
   - Labels: use existing repo labels or configured labels; do not invent remote labels silently.

4. Decide output mode.
   - If the user asked to create GitHub issues and `gh` is available, create them with explicit commands.
   - If not, output markdown issue drafts ready to paste.
   - For local issue tracking, write files only when the user asked for local artifacts.

5. Verify.
   - Confirm every source requirement maps to an issue or explicit non-goal.
   - Confirm no issue requires another engineer to make hidden product decisions.
