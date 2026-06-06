---
name: grill-with-docs
description: Challenge a plan against the repository domain model, CONTEXT.md, and ADRs. Use when the user wants rigorous grilling of a design, sharper terminology, or inline updates to domain and decision docs.
---

# Grill With Docs


Use this skill to stress-test a plan against the codebase's documented model.
It is a discussion and documentation workflow, not a code implementation shortcut.

## Codex Coordination

- Obey the active collaboration mode. In Plan Mode, inspect and propose only; do not mutate files, issues, branches, or external systems.
- Read local `AGENTS.md`, `CLAUDE.md`, and nested instructions before repository writes.
- Preserve unrelated dirty work. Never bulk-stage, bypass hooks, or run destructive commands without explicit approval.
- If another active skill gives stricter verification or safety rules, follow the stricter rule.

Doc edits are allowed only when the user asked for them and the active mode permits mutation. Otherwise, return proposed `CONTEXT.md` or ADR changes as a patch-style plan.

## Output Contract

Lead with the strongest challenges to the plan, then list terminology fixes, missing decisions, proposed doc changes, and open questions. If files were changed, include exact paths and verification performed.


## Source Fidelity Notes

The upstream behavior is a grilling interview, not a passive review.

- Ask the questions one at a time, wait for feedback, and provide a recommended answer for each question.
- If a question can be answered by exploring the codebase, explore the codebase instead.
- Support single-context repos with `CONTEXT.md` and multi-context repos with `CONTEXT-MAP.md`.
- Create files lazily: `CONTEXT.md` only when a term is resolved, ADRs only when a decision actually needs one.
- Challenge against the glossary when user terms conflict with existing language.
- Update CONTEXT.md inline when terms are resolved, but keep it devoid of implementation details.
- Offer ADRs sparingly: Hard to reverse, Surprising without context, and the result of a real trade-off must all be true.
## Workflow

1. Ground in source material.
   - Read local instructions, `CONTEXT.md` if present, `docs/adr/` if present, and the files named by the user.
   - If those docs are missing, inspect the relevant code/docs enough to identify the current vocabulary.

2. Extract the domain language.
   - List the nouns, states, invariants, and boundaries the plan relies on.
   - Mark unclear or overloaded terms instead of inventing new names.

3. Grill the plan.
   - Challenge the plan against existing invariants, module boundaries, ADRs, and user-visible behavior.
   - Ask only questions that materially change the plan.
   - Prefer direct challenges: what breaks, what is ambiguous, what contract is missing, what decision is undocumented.

4. Revise artifacts when requested.
   - Update `CONTEXT.md` for durable vocabulary or domain model changes.
   - Add or amend ADRs for architectural decisions with consequences.
   - Keep edits scoped; do not rewrite broad docs for style.

5. Finish with a decision log.
   - Summarize accepted changes, rejected alternatives, open risks, and exact docs touched.

## References

- `references/context-format.md`: concise `CONTEXT.md` structure.
- `references/adr-format.md`: ADR shape for decisions discovered during grilling.
