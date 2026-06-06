---
name: to-prd
description: Turn the current conversation or rough idea into a concise PRD and optionally submit it as a GitHub issue. Use when the user wants product requirements captured for implementation.
---

# To PRD


Use this skill to convert conversation context into a product requirements document.

## Codex Coordination

- Obey the active collaboration mode. In Plan Mode, inspect and propose only; do not mutate files, issues, branches, or external systems.
- Read local `AGENTS.md`, `CLAUDE.md`, and nested instructions before repository writes.
- Preserve unrelated dirty work. Never bulk-stage, bypass hooks, or run destructive commands without explicit approval.
- If another active skill gives stricter verification or safety rules, follow the stricter rule.

Submitting the PRD to GitHub or another tracker requires an explicit user request. Otherwise, provide the PRD body and recommended title only.

## Output Contract

Return a concise PRD with problem, audience, goals, non-goals, requirements, acceptance criteria, UX/API/data implications, risks, open questions, and test/rollout expectations.


## Source Fidelity Notes

Do NOT interview the user when this skill is invoked; synthesize from current conversation context and repo understanding.

Sketch out the major modules to build or modify, actively looking for a deep module: substantial behavior behind a simple, testable interface.

Check with the user that modules match expectations and Check with the user which modules they want tests written for.

The PRD template includes Problem Statement, Solution, User Stories, Implementation Decisions, Testing Decisions, Out of Scope, and Further Notes. If publishing to an issue tracker, apply the ready-for-agent triage label.
## Workflow

1. Gather context.
   - Read the conversation, referenced files, existing docs, and current product behavior.
   - Separate facts from assumptions.

2. Draft the PRD.
   - Problem and audience.
   - Goals and non-goals.
   - User stories or jobs.
   - Requirements and acceptance criteria.
   - UX/API/data changes if known.
   - Risks, dependencies, and open questions.
   - Test and rollout expectations.

3. Keep it implementable.
   - Avoid speculative edge cases unless they prevent a concrete implementation mistake.
   - Mark unresolved product decisions clearly.

4. Submit only when requested.
   - If the user asked for a GitHub issue, use `gh issue create` or the repo's configured tracker.
   - Otherwise, provide the PRD body and recommended title.

5. Verify mapping.
   - Ensure every major user request is represented or explicitly out of scope.
