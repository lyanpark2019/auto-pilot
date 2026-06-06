---
name: harness-qa
description: Invoke the harness-evaluator subagent for sprint contract review or implementation QA. Third stage of the 3-agent autonomous coding harness (Planner → Generator → Evaluator).
argument-hint: "<sprint-number>"
context: fork
agent: harness-evaluator
---

Evaluate sprint $ARGUMENTS.

**Mode A** (if `.claude/harness/sprints/$ARGUMENTS-contract.md` exists but `-handoff.md` does NOT):
Review the contract. Verify scope matches spec; all required sections are present (Goal, Public interface, Deep module / internal location, Invariants, Write set, Tests / checks, Rollback surface, Evaluator gate before merge, Out of scope, Sign-off); invariants are falsifiable; tests/checks are concrete and observable; the write set calls out locked files; rollback surface names revert path and user-visible risk; "Out of scope" doesn't punt critical work. Sign off (append `Evaluator: approved`) or reject with specific reason.

**Mode B** (if `-handoff.md` exists):
First confirm the actual diff is a subset of the contract's approved write set (FAIL on any out-of-set path unless the contract was revised and re-approved). Then exercise the running app via Playwright CLI / hurl / curl against each testable behavior in the contract. Score against 7 criteria (Feature completeness, Functionality, Visual design, Code quality, Contract/write-set compliance, Rollback surface, AI integration). Hard threshold each — any FAIL blocks sprint completion.

Write report to `.claude/harness/sprints/$ARGUMENTS-eval.md` and update `progress.json` (`completed` on PASS, `needs_revision` on FAIL).

Be skeptical. Don't approve based on code-reading alone. Show run log, screenshot, or curl output for each verdict.
