# wiki-harness-engineering template

Skeleton for the Obsidian-vault tree that `scripts/codex-analyze.sh` publishes. The script generates dynamic pages (layers, friction-map, deepening-backlog) from codex worker output. This template provides:

- the directory layout (mirrored verbatim into the target vault)
- placeholder pages the PM authors directly (index, 3 principle pages)
- frontmatter spec + section spec every dynamic page must follow

## Tree

```
wiki/harness-engineering/
├── index.md                       PM-authored, see index.template.md
├── principles/
│   ├── 01-doctrine.md             PM-authored, copy from references/codex-multi-worker-doctrine.md
│   ├── 02-supervisor-pattern.md   PM-authored, see principles/02-supervisor-pattern.template.md
│   └── 03-message-bus.md          PM-authored, see principles/03-message-bus.template.md
├── layers/
│   ├── interface.md               worker-1 → 02-draft (see layers/_layer.template.md)
│   ├── application.md             worker-2 → 02-draft
│   ├── domain.md                  worker-3 → 02-draft
│   ├── infrastructure.md          worker-4 → 02-draft
│   └── cross-cutting.md           worker-5 → 02-draft
├── deepening-backlog.md           PM, aggregated from 5 worker discover outputs
└── friction-map.md                PM, top-N issues integrated across layers
```

## Frontmatter spec (every page)

```yaml
---
type: <harness-engineering-index | harness-doctrine | harness-pattern | layer | deepening-backlog | friction-map>
generated: <YYYY-MM-DD>
sources: [<source-ids>]            # codex ticket IDs or notebook IDs
# optional per type:
layer: <interface|application|domain|infrastructure|cross-cutting>
pattern: <supervisor|file-message-bus|...>
---
```

## Section spec for `layers/*.md`

Worker 02-draft MUST emit these sections in order:

1. `# <Layer Name>`
2. `## Purpose` (1 paragraph; cite [[principles/01-doctrine]] principles applied)
3. `## Modules` (table: path | role | depth reading)
4. `## Public Interface Surface` (path:line bullets)
5. `## Seams` (boundary with adjacent layers; DIP direction)
6. `## Deepening Backlog` (3–5 entries: problem + solution + deletion test)
7. `## Cross-links` (wikilinks to other vault pages)

Mandatory gates (PM enforces, ticket JSON specifies):
- Every paragraph has `path:line` citation
- Deletion test passes: "deleting this paragraph would lose info that callers/users need"
- `Module / Interface / Seam / Depth / Leverage / Locality` vocabulary used per `improve-codebase-architecture` skill

## Section spec for `index.md`

1. `# Harness Engineering — <project>`
2. `## What is "Harness Engineering"` (3-layer table: prompt vs context vs harness)
3. `## How <project> uses harness engineering` (surface table: CLAUDE.md, hooks, gates)
4. `## Tree` (the layout above)
5. `## Reading order` (4 paths by intent)
6. `## Cross-vault` (links to sibling vaults if applicable)
7. `## Provenance` (link to ledger + doctrine reference)

## Section spec for `friction-map.md`

1. `# Friction Map`
2. `## Top Friction (Cross-Layer, P0~P1)` (table: rank | issue | layer | file evidence | doctrine link)
3. `## Module Depth Reading` (per layer; load-bearing vs shallow)
4. `## SSoT verification` (single source of truth audit results)
5. `## Architecture Tests coverage` (what is gated, what is not)
6. `## Deepening Candidates Integrated` (top-N pointer to deepening-backlog)
7. `## vault wiki/harness-engineering tree` (provisional tree)

## Section spec for `deepening-backlog.md`

1. `# Deepening Backlog`
2. `## P0 — Cross-layer` (top 3–5)
3. `## P1 — Single layer` (table)
4. `## P2 — Defer / hypothetical` (table with reasons)
5. `## How to consume this list` (RPI cycle per [[principles/01-doctrine#P12]])
