---
name: harness-qa
description: Invoke the harness-evaluator subagent for sprint contract review or implementation QA. Third stage of the 3-agent autonomous coding harness (Planner → Generator → Evaluator).
argument-hint: "<sprint-number>"
context: fork
agent: harness-evaluator
---

Evaluate sprint $ARGUMENTS.

**Mode A** (if `.claude/harness/sprints/$ARGUMENTS-contract.md` exists but `-handoff.md` does NOT):
Review the contract. Verify scope matches spec, testable behaviors are concrete, "Out of scope" doesn't punt critical work. Sign off (append `Evaluator: approved`) or reject with specific reason.

**Mode B** (if `-handoff.md` exists):
Exercise the running app via Playwright CLI / hurl / curl against each testable behavior in the contract. Score against 5 criteria (Feature completeness, Functionality, Visual design, Code quality, AI integration). Hard threshold each — any FAIL blocks sprint completion.

Write report to `.claude/harness/sprints/$ARGUMENTS-eval.md` and update `progress.json` (`completed` on PASS, `needs_revision` on FAIL).

Be skeptical. Don't approve based on code-reading alone. Show run log, screenshot, or curl output for each verdict.
