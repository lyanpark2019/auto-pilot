---
name: harness-plan
description: Invoke the harness-planner subagent to expand a short product prompt into a full feature spec. First stage of the 3-agent autonomous coding harness (Planner → Generator → Evaluator).
argument-hint: "<1-4 sentence product description>"
context: fork
agent: harness-planner
---

Expand this prompt into a full product spec written to `.claude/harness/spec.md`:

$ARGUMENTS

Read existing `CLAUDE.md` and `docs/adr/` first to understand constraints. Be ambitious about scope; conservative about technical detail. Identify natural AI-feature integration points. Output a sprint breakdown table at the end.

After completion, invoke `/harness-build` to start sprint generation.
