---
name: harness-build
description: Invoke the harness-generator subagent to build the next un-finished sprint from .claude/harness/spec.md. Negotiates contract with harness-evaluator before coding. Second stage of the 3-agent autonomous coding harness.
context: fork
agent: harness-generator
---

Build the next sprint from the spec.

Read state:
- `.claude/harness/spec.md` — Planner's spec
- `.claude/harness/progress.json` — which sprints are done
- `.claude/harness/budget.json` — token budget if set

Pick the lowest-numbered sprint not marked `completed`. Write a sprint contract to `.claude/harness/sprints/{NN}-contract.md` and wait for `/harness-qa` sign-off. Then implement, self-test via `stop-quality-gate.sh`, and write handoff doc.

If all sprints complete: report and exit.
