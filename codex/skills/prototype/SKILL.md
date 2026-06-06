---
name: prototype
description: Build a throwaway prototype to explore a design. Use for runnable terminal prototypes, state-machine experiments, business-logic probes, or multiple UI variations before committing to production code.
---

# Prototype


Use this skill when the user wants to explore behavior or UI before production implementation.
The prototype is disposable unless the user explicitly asks to promote it.

## Codex Coordination

- Obey the active collaboration mode. In Plan Mode, inspect and propose only; do not mutate files, issues, branches, or external systems.
- Read local `AGENTS.md`, `CLAUDE.md`, and nested instructions before repository writes.
- Preserve unrelated dirty work. Never bulk-stage, bypass hooks, or run destructive commands without explicit approval.
- If another active skill gives stricter verification or safety rules, follow the stricter rule.

Prototype work may create throwaway files only in permitted writable locations. Repository prototypes require an explicit user request and a clearly marked prototype path.

## Output Contract

Report the decision question, prototype type, artifact path, run command or URL, observations, what was proven or disproven, cleanup status, and what would be needed to promote it.


## Source Fidelity Notes

A prototype is throwaway code that answers a question. Pick Logic Prototype for business logic, state transitions, or data shape; pick UI Prototype for visual direction.

For UI, generate radically different variants on a single route with a `?variant=` switch and a floating bottom bar. Prefer embedding in an existing page; create a new throwaway route only as a last resort.

Rules that apply to both: one command to run, No persistence by default, Surface the state after every action or variant switch, and Delete or absorb when the question is answered.
## Choose Prototype Type

- Logic prototype: terminal app, script, state machine, parser, or fixture runner.
- UI prototype: several distinct variations toggleable from one route or command.
- Interaction prototype: minimal runnable surface to test flow, timing, or ergonomics.

## Workflow

1. Define the question.
   - What decision should the prototype answer?
   - What is explicitly not being validated?

2. Keep it isolated.
   - Prefer `/private/tmp` for throwaway work.
   - If the prototype must live in the repo, put it under an obvious prototype path and avoid production imports unless required.
   - For outside-repo temp paths, do not rely on project-scoped patch/edit tools. Create the temp artifact with an explicit command or script, then report the artifact path and cleanup status.

3. Build the smallest runnable thing.
   - Use existing project tooling when that lowers setup cost.
   - For UI, make variations easy to compare and verify with screenshots when possible.
   - For logic, include fixture inputs and clear output.

4. Evaluate.
   - Run it.
   - Capture what it proves, what it disproves, and what remains unknown.

5. Clean up or hand off.
   - Delete throwaway files unless the user asks to keep them.
   - If promoting to production, switch to the appropriate implementation skill and write tests.

## References

- `references/logic.md`: terminal and state/business logic prototype patterns.
- `references/ui.md`: UI variation prototype patterns.
