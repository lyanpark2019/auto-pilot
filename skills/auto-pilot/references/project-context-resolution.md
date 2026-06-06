<!-- Shared contract: project-context resolution order (system heart ①).
     SoT for the 4-step order = docs/specs/2026-06-06-unified-coding-system-design.md
     "System heart" section. This file is the wire-in copy agents read; it cites,
     never re-derives. Lives under skills/auto-pilot/references/ (NOT agents/ —
     recursive agent auto-discovery would surface it as a ghost agent, the
     review-core.md defect). -->

# Project-Context Resolution — 4-step order (read before scanning any repo)

Whenever an agent needs project understanding (PM PLAN ingestion, doc-management
Phase-0/authoring, retro read-side, swarm-explorer mapping, setup-harness Step 1),
resolve in THIS order:

1. **Obsidian vault** `~/Documents/Knowledge/wiki/projects/<repo-slug>/` — read
   `_graph/GRAPH_REPORT.md`, `intent/` (decisions · gotchas · history), hot cache.
   Vault hit = cheapest AND carries Why. Slug = repo directory name lowercased
   (e.g. `pickl-api`). Vault absent → step 2.
2. **Repo graph** `<repo>/graphify-out/` — `graphify query` / `graphify explain`
   against the existing graph. Staleness check first: the graph's built commit vs
   `git rev-parse HEAD`; a `needs_update` marker (written by
   `hooks/doc-sync-update.sh`) means rebuild before trusting it (step 3).
3. **Build the code-only graph** — `graphify update .` (AST-only, key-free), then
   query it. Code-only filter rules: `skills/doc-management/references/rebuild-phases.md`
   Phase 1 (single source — do not re-derive).
4. **Raw source scan** — last resort only. Record WHY steps 1–3 missed (no vault?
   stale graph? graph lacks the answer?) so the gap gets fixed (vault export /
   graph rebuild), not silently re-paid next run.

Rule: vault first, codebase last — never invert. A run that needed step 4 is a
retro-worthy event: note it so the knowledge layer grows.

## Wire-in points (each cites this file; none re-derives the order)

- `agents/pm-orchestrator.md` — PLAN ingestion
- `skills/doc-management/SKILL.md` — Phase-0 diagnosis / authoring inputs
- `agents/retro.md` — read-side (what context existed when the round ran)
- `agents/swarm-explorer.md` — swarm bootstrap mapping
- `skills/setup-harness/SKILL.md` Step 1 — project scan

## Retro write contract (system heart ② — closes the loop)

Retro writes lessons **append-only + evidence-cited** to:
- vault `intent/gotchas/` (if the project vault exists), AND
- repo `.claude/insights.md` (create if absent),
- plus a one-line pointer into session memory.

Never rewrite prior entries. Next run's step 1 reads what retro wrote — that is
the whole point of the order above.
