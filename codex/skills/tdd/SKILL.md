---
name: tdd
description: Test-driven development with a red-green-refactor loop. Use when the user explicitly asks for TDD, test-first implementation, red-green-refactor, or one vertical behavior slice at a time.
---

# Test-Driven Development


Use this skill when the user wants test-first development.
The core rule is one behavior slice at a time: one failing test, minimal code, passing test, then repeat.

## Codex Coordination

- Obey the active collaboration mode. In Plan Mode, inspect and propose only; do not mutate files, issues, branches, or external systems.
- Read local `AGENTS.md`, `CLAUDE.md`, and nested instructions before repository writes.
- Preserve unrelated dirty work. Never bulk-stage, bypass hooks, or run destructive commands without explicit approval.
- If another active skill gives stricter verification or safety rules, follow the stricter rule.

If `superpowers:test-driven-development` is also active, follow its red-green-refactor requirements and use this skill as the local checklist for slice shape and test quality.

## Output Contract

For each completed slice, report the behavior, public seam, RED command and intended failure, GREEN command and passing evidence, refactor steps, and remaining untested behaviors.


## Source Fidelity Notes

Good tests verify behavior through public interfaces. Bad tests assert implementation details, private methods, internal collaborators, or call order.

Horizontal Slices are an anti-pattern: do not write all tests first and all implementation second. Use vertical tracer bullets instead.

Before writing code, Confirm with user what interface changes are needed, confirm which behaviors to test, list behavior tests, and Get user approval on the plan.

You can't test everything; prioritize critical paths and complex logic. The first cycle is a Tracer Bullet: one behavior, one failing test, minimal code, then green. Never refactor while RED.
## Principles

- Test observable behavior through public interfaces.
- Prefer integration-style tests that survive refactors.
- Avoid tests coupled to private methods, file layout, or internal collaborators.
- Never write all tests first and all implementation second.
- Never refactor while tests are red.

## Workflow

1. Plan the first vertical slice.
   - Read local instructions, current tests, public interfaces, and relevant docs.
   - Identify the behavior, public seam, and expected observable result.
   - If the interface is ambiguous, clarify before writing code.

2. Red.
   - Add exactly one focused test for one behavior.
   - Run the narrow test command and confirm it fails for the intended reason.

3. Green.
   - Implement the smallest code change that passes that test.
   - Run the same test and then the relevant broader test set.

4. Repeat.
   - Add the next behavior only after the previous one is green.
   - Let each cycle update the next test based on what the code revealed.

5. Refactor.
   - Refactor only with tests green.
   - Run tests after each meaningful refactor step.

6. Report.
   - Include the red and green commands, behaviors covered, and any behavior intentionally left untested.

## References

- `references/tests.md`: behavior-focused test examples.
- `references/mocking.md`: mocking rules.
- `references/interface-design.md`: testable interface prompts.
- `references/deep-modules.md`: module-depth prompts.
- `references/refactoring.md`: safe refactor checklist.
