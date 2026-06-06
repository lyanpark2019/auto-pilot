---
name: diagnose
description: Disciplined diagnosis loop for hard bugs and performance regressions. Use for debugging failures, broken behavior, flaky tests, or slow paths where the agent must reproduce, minimize, hypothesize, instrument, fix, and regression-test.
---

# Diagnose


Use this skill when the task is to debug a real failure or performance regression.
The goal is not to guess the fix; the goal is to build a pass/fail loop that makes the cause testable.

## Codex Coordination

- Obey the active collaboration mode. In Plan Mode, inspect and propose only; do not mutate files, issues, branches, or external systems.
- Read local `AGENTS.md`, `CLAUDE.md`, and nested instructions before repository writes.
- Preserve unrelated dirty work. Never bulk-stage, bypass hooks, or run destructive commands without explicit approval.
- If another active skill gives stricter verification or safety rules, follow the stricter rule.

If `superpowers:systematic-debugging` is also active, use that skill for the overall debugging discipline and this skill for the concrete feedback-loop, hypothesis, and cleanup checklist.

## Output Contract

Report the reproduction loop, exact symptom, ranked hypotheses, probes run, fix summary, regression coverage, verification commands, and residual risk. Do not claim the bug is fixed without fresh command output from the original loop.


## Source Fidelity Notes

The upstream skill treats the feedback loop as the center of the work: a fast, deterministic, agent-runnable pass/fail signal is more important than early hypotheses.

- Iterate on the loop itself: make it faster, sharper, and more deterministic before debugging deeply.
- Non-deterministic bugs need higher reproduction rate through loops, stress, parallel runs, sleeps, or timing-window narrowing.
- Do not proceed to Phase 2 until the loop reproduces the user's exact symptom.
- A regression test must use a correct seam that exercises the real bug pattern at the call site.
- After cleanup, ask what would have prevented this bug and hand off architecture findings only after the fix is understood.
## Workflow

1. Ground in the repo before changing anything.
   - Read local instructions, `git status --short`, relevant docs, and the entrypoints around the symptom.
   - Preserve unrelated dirty work and do not bypass hooks or checks.

2. Build the feedback loop first.
   - Prefer, in order: failing test, focused CLI command, HTTP/curl script, browser automation, replayed trace, throwaway harness, fuzz/property loop, bisection harness, or a human-in-the-loop script.
   - Make the loop deterministic and as narrow as possible while still reproducing the user's symptom.
   - If no loop is possible, stop and ask for a log, trace, fixture, environment access, or permission for temporary instrumentation.

3. Reproduce the exact bug.
   - Confirm the loop fails for the same symptom the user reported.
   - Capture exact error text, wrong output, timing, or trace evidence.

4. Rank hypotheses before testing.
   - Write 3 to 5 falsifiable hypotheses.
   - State each prediction as: if this is the cause, changing or observing this boundary will prove it.
   - Share the ranked list when the probe would be invasive; otherwise proceed with the top hypothesis.

5. Instrument one boundary at a time.
   - Prefer debugger/REPL inspection, then targeted logs.
   - Tag temporary logs with a unique `[DEBUG-...]` prefix and remove them before finishing.
   - For performance, measure first with a repeatable benchmark, profile, query plan, or timing harness.

6. Fix with a regression check.
   - Add the regression test before the fix when a correct seam exists.
   - If no correct seam exists, document that as an architecture gap.
   - Apply the smallest fix that makes the failing loop pass.

7. Clean up before reporting.
   - Re-run the original loop and the regression test.
   - Remove debug logs and throwaway files, or move kept diagnostics into an explicitly named debug location.
   - State the hypothesis that proved true and the command output that verifies the fix.

## Resources

- `scripts/hitl-loop.template.sh`: template for a structured manual reproduction loop when automation cannot drive the final trigger.
