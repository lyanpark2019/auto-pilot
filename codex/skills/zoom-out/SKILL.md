---
name: zoom-out
description: Give broader context on an unfamiliar code area, plan, or decision. Use when the user asks to zoom out, explain the bigger picture, or connect local details to system architecture.
---

# Zoom Out


Use this skill when the user needs a higher-level map before deciding what to do next.

## Codex Coordination

- Obey the active collaboration mode. In Plan Mode, inspect and propose only; do not mutate files, issues, branches, or external systems.
- Read local `AGENTS.md`, `CLAUDE.md`, and nested instructions before repository writes.
- Preserve unrelated dirty work. Never bulk-stage, bypass hooks, or run destructive commands without explicit approval.
- If another active skill gives stricter verification or safety rules, follow the stricter rule.

This skill is explanatory by default. Do not edit code or docs unless the user turns the explanation into an implementation request.

## Output Contract

Return a system map: local responsibility, upstream callers, downstream dependencies, data flow, tests/docs, common failure modes, and recommended next moves.


## Source Fidelity Notes

The upstream prompt is intentionally small: "Go up a layer of abstraction." Return a map of all the relevant modules and callers, using the project's domain glossary vocabulary.
## Workflow

1. Identify the local object.
   - File, module, issue, plan, error, or feature under discussion.

2. Trace outward.
   - Find callers, owners, tests, docs, data flow, side effects, and related ADRs.
   - Prefer `rg`, manifests, and entrypoints over broad reading.

3. Explain at the right altitude.
   - What this area does.
   - Why it exists.
   - What depends on it.
   - What usually goes wrong here.
   - What decisions are safe versus risky.

4. End with concrete next moves.
   - Recommend whether to inspect, test, refactor, document, or leave it alone.
   - Keep the answer concise unless the user asks for a deep dive.
