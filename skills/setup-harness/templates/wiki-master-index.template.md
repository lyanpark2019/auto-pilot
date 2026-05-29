---
type: wiki-master-index
domain: {{PROJECT_NAME}}
generated: {{DATE}}
sub_trees: [harness-engineering]
---

# {{PROJECT_NAME}}-Vault — wiki ToC

Root master index for all `wiki/` sub-trees. Each sub-tree has its own `index.md`. Use [[..|_index]] for the vault top-level entry.

## Sub-trees

| Sub-tree | Pattern | Entry | Maintained by |
|----------|---------|-------|---------------|
| `harness-engineering/` | doctrine + per-layer analysis + deepening backlog + friction map | [[harness-engineering/index]] | `setup-harness/scripts/codex-analyze.sh` (Opus PM + Codex×N) |
<!-- HARNESS-ANALYZE-INSERT: additional sub-trees auto-merged by codex-analyze.sh -->

## Conventions

- Every page MUST have YAML frontmatter (`type:` + `generated:` minimum).
- Wikilinks use Obsidian relative syntax (`[[sub-tree/page]]` or `[[../sibling]]`).
- Layer pages MUST cite `path:line` for every claim; PM enforces via `codex-analyze.sh verify`.
- Pages added by Codex workers always live in `outbox/worker-N/02-draft.md` before publish; PM gate first.

## Provenance

- This `wiki/` root was opened {{DATE}} by `setup-harness` skill's Codex multi-worker mode.
- Ledger: `.planning/harness-rewrite/ledger.md` (repo-local; not in vault).
- Doctrine SoT: `${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/references/codex-multi-worker-doctrine.md` (mirrored into `.planning/harness-rewrite/refs/doctrine.md` per project).
