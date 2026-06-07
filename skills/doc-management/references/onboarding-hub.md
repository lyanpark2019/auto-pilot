# AI / Developer onboarding hub

Purpose: make a project easy for new developers and AI agents to understand without trusting stale prose or spending the first hour grepping randomly.

This reference distills the shared workflow at `/Users/lyan/Documents/Knowledge/wiki/ai/workflows/graphify-docs-drift-refresh.md` and Karpathy's LLM Wiki pattern into the reusable `doc-management` rule set.

## Persistent wiki contract

The target is a **persistent, compounding wiki**, not one-off RAG over raw files. Every useful answer should either update an existing page, become a new page, or be intentionally discarded as non-durable.

| Layer | Meaning |
|---|---|
| Raw sources | Immutable source documents, code, logs, specs, transcripts, and raw notes. |
| Generated wiki | LLM-maintained markdown synthesis: overview, entity/concept pages, flow docs, comparisons, onboarding. |
| Schema | `CLAUDE.md`, `AGENTS.md`, docs index, and workflow references that tell agents how to maintain the wiki. |

Required operations:

- **Ingest:** integrate new source evidence into existing pages, not just append summaries.
- **Query:** answer from the wiki + graph, then file durable answers back into the wiki when reusable.
- **Lint:** check contradictions, stale claims, orphan pages, missing links, and outdated graph state.
- **Index/log:** keep an `index.md` or docs hub for navigation; use `log.md` or commit/review history for chronology.

## Output contract

A healthy docs tree has one obvious first-read path:

- `docs/README.md` — docs map and source-of-truth order.
- `docs/onboarding/README.md` or `docs/onboarding.md` — AI / Developer onboarding hub.
- `docs/architecture/` or equivalent architecture anchors — topic pages, not per-module mirrors.
- `docs/flows/` or equivalent — important product/data/ops flows.
- `docs/runbooks/` — operations and graph/docs refresh workflows.
- `docs/meta/` — provenance, audit reports, health assessments.

Small repos may collapse folders, but must still have a single onboarding entry.

## What / Why split

- `What`: current modules, calls, routes, commands, schema, data flow. Source = graphify + source read.
- `Why`: decisions, constraints, incidents, trade-offs. Source = ADRs, history, retros, human-authored docs.

Never delete `Why` just because current code changed. First classify whether the prose is historical rationale or a current implementation claim.

## Case A / Case B triage

| Case | Meaning | Handling |
|---|---|---|
| Case A | Invalid, stale, retired, or dangerous docs | Quarantine/archive or mark historical. Extract `Why` only. Rebuild current `What` from graphify + source. |
| Case B | Valid or mostly-correct docs | Keep. Verify generated facts. Surgically update only stale paths, symbols, routes, commands, or flow descriptions. |

If unsure, treat the doc as Case A for current facts: do not cite it as proof until graphify and source confirm it.

## Graphify command contract

Use these current CLI forms:

```bash
# Normal code graph refresh; no LLM required.
graphify update . --force

# Full headless semantic rebuild; use when docs/papers/media or deep extraction matter.
graphify extract . --mode deep

# Scoped understanding.
graphify query "<question>" --graph graphify-out/graph.json --budget 3000
graphify explain "<symbol>" --graph graphify-out/graph.json
graphify path "<A>" "<B>" --graph graphify-out/graph.json
graphify affected "<symbol>" --graph graphify-out/graph.json --depth 1
```

Do not document export subcommands that the installed CLI does not expose.

## Authoring loop

For each doc or onboarding section:

1. Identify current-fact claims: paths, symbols, routes, commands, imports/calls, state files, schema names.
2. Run scoped `graphify query` / `graphify explain` / `graphify path`.
3. Read the source files surfaced by graphify.
4. Edit only incorrect `What` unless the user approved a full REBUILD.
5. Preserve `Why`, but label historical rationale as historical when needed.
6. Add a short verification note when useful; avoid noisy notes on every paragraph.
7. Run the repo doc guard and `git diff --check`.

## Onboarding hub required sections

- Start-here path for humans and AI agents.
- Architecture in 10 minutes.
- Source-of-truth order.
- Graphify freshness and query commands.
- Task routing table.
- Maintenance safety checklist.
- Verification checklist.
- Known traps and how to avoid them.

## External Knowledge vaults

If a project stores graphs outside the repo, the onboarding hub must name the explicit graph path and all commands must pass `--graph <absolute graph.json>`. If the graph lives in repo-local `graphify-out/`, say that instead. Do not let agents guess.

## Done definition

- A new developer can find the right subsystem in under 10 minutes.
- An AI agent can answer “where do I start?” without reading stale audit history first.
- The hub tells agents how to refresh/check graph freshness.
- Current facts are graph/source-backed; rationale is preserved but not confused with current implementation.
- Mechanical docs checks pass, and residual semantic risk is reported honestly.
