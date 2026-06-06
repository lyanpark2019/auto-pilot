---
name: improve-codebase-architecture
description: Find deepening opportunities in a codebase using domain language and ADRs. Use for architecture reviews, module boundary analysis, interface simplification, or refactor planning.
---

# Improve Codebase Architecture


Use this skill to discover architectural improvements before or after feature work.
It should produce evidence-backed opportunities, not broad speculative rewrites.

## Codex Coordination

- Obey the active collaboration mode. In Plan Mode, inspect and propose only; do not mutate files, issues, branches, or external systems.
- Read local `AGENTS.md`, `CLAUDE.md`, and nested instructions before repository writes.
- Preserve unrelated dirty work. Never bulk-stage, bypass hooks, or run destructive commands without explicit approval.
- If another active skill gives stricter verification or safety rules, follow the stricter rule.

This skill defaults to analysis. Implementation requires a separate explicit user request or a follow-up implementation plan.

## Output Contract

Return ranked opportunities with evidence paths, current cost, proposed interface or boundary change, migration shape, tests needed, and non-goals. Mark ADR-worthy decisions separately from quick refactors.


## Source Fidelity Notes

Use the upstream architecture vocabulary exactly: Module, Interface, Implementation, Depth, Seam, Adapter, Leverage, and Locality.

- Apply the deletion test to suspected shallow modules.
- Produce an HTML report in the OS temp directory for candidate reviews when the user wants a full architecture pass.
- The report should include before/after visualization, benefits framed as Leverage and Locality, and a recommendation strength.
- Do NOT propose interfaces yet during the candidate report. First ask: "Which of these would you like to explore?"
- After a candidate is selected, enter the Grilling loop and update `CONTEXT.md` or ADRs only as real decisions crystallize.
## Workflow

1. Ground in the domain.
   - Read local instructions, `CONTEXT.md`, ADRs, and relevant entrypoints.
   - If docs are missing, derive vocabulary from code and tests and note the gap.

2. Inventory boundaries.
   - Identify public interfaces, orchestration layers, data owners, adapters, and side-effect boundaries.
   - Prefer `rg --files`, dependency manifests, tests, and import graphs over intuition.

3. Find deepening opportunities.
   - Look for shallow modules, duplicated policy, hidden coupling, leaky abstractions, scattered validation, and tests that must know internals.
   - Tie each opportunity to a concrete cost: bug risk, test fragility, feature friction, performance, or operational risk.

4. Rank proposals.
   - Recommend small, reversible changes first.
   - Separate "do now" work from ADR-worthy direction changes.
   - Avoid refactors that do not pay for themselves in current goals.

5. Produce the architecture report.
   - Include evidence paths, proposed interface, migration shape, tests, and explicit non-goals.
   - Do not edit code unless the user asked for implementation.

## References

- `references/deepening.md`: module-depth checklist.
- `references/interface-design.md`: interface review prompts.
- `references/language.md`: domain-language extraction.
- `references/html-report.md`: optional report structure for large reviews.
