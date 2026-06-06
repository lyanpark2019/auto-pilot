---
description: >
  3-agent autonomous coding harness router — plan (harness-planner expands a product
  prompt into .claude/harness/spec.md), build (harness-generator implements the next
  sprint under contract), qa (harness-evaluator reviews contract / QAs implementation).
  Replaces /harness-plan /harness-build /harness-qa.
argument-hint: "<plan|build|qa> [plan: product description | qa: sprint-number]"
---

# /harness

Route to the appropriate harness subagent. Each mode dispatches via the Task tool into the matching agent (harness-planner / harness-generator / harness-evaluator), which runs in its own isolated context with the body below as its prompt.

## Routing

| `$1`  | Agent dispatched     | Args forwarded            |
|-------|----------------------|---------------------------|
| plan  | harness-planner      | `$2..` = product description |
| build | harness-generator    | (none)                    |
| qa    | harness-evaluator    | `$2` = sprint number      |
| (other/empty) | (print usage + state) | —               |

---

## Usage

```
/harness plan <1-4 sentence product description>
/harness build
/harness qa <sprint-number>
```

If `$1` is empty or unrecognised: print this usage block and read
`.claude/harness/progress.json` to show current sprint state.

---

## mode: plan

Use the `harness-planner` agent with the following prompt:

> Expand this prompt into a full product spec written to `.claude/harness/spec.md`:
>
> $2
>
> Read existing `CLAUDE.md` and `docs/adr/` first to understand constraints. Be ambitious about scope; conservative about technical detail. Identify natural AI-feature integration points. Output a sprint breakdown table at the end.
>
> After completion, invoke `/harness build` to start sprint generation.

---

## mode: build

Use the `harness-generator` agent with the following prompt:

> Build the next sprint from the spec.
>
> Read state:
> - `.claude/harness/spec.md` — Planner's spec
> - `.claude/harness/progress.json` — which sprints are done
> - `.claude/harness/budget.json` — token budget if set
>
> Pick the lowest-numbered sprint not marked `completed`. Write a sprint contract to `.claude/harness/sprints/{NN}-contract.md` and wait for `/harness qa` sign-off. Then implement, self-test via `stop-quality-gate.sh`, and write handoff doc.
>
> If all sprints complete: report and exit.

---

## mode: qa

Use the `harness-evaluator` agent with the following prompt:

> Evaluate sprint $2.
>
> **Mode A** (if `.claude/harness/sprints/$2-contract.md` exists but `-handoff.md` does NOT):
> Review the contract. Verify scope matches spec; all required sections are present (Goal, Public interface, Deep module / internal location, Invariants, Write set, Tests / checks, Rollback surface, Evaluator gate before merge, Out of scope, Sign-off); invariants are falsifiable; tests/checks are concrete and observable; the write set calls out locked files; rollback surface names revert path and user-visible risk; "Out of scope" doesn't punt critical work. Sign off (append `Evaluator: approved`) or reject with specific reason.
>
> **Mode B** (if `-handoff.md` exists):
> First confirm the actual diff is a subset of the contract's approved write set (FAIL on any out-of-set path unless the contract was revised and re-approved). Then exercise the running app via Playwright CLI / hurl / curl against each testable behavior in the contract. Score against 7 criteria (Feature completeness, Functionality, Visual design, Code quality, Contract/write-set compliance, Rollback surface, AI integration). Hard threshold each — any FAIL blocks sprint completion.
>
> Write report to `.claude/harness/sprints/$2-eval.md` and update `progress.json` (`completed` on PASS, `needs_revision` on FAIL).
>
> Be skeptical. Don't approve based on code-reading alone. Show run log, screenshot, or curl output for each verdict.
