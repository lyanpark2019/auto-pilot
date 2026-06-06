# codebase-perfection-loop — DEPRECATED

DEPRECATED — superseded by adversarial-review-loop (codebase mode) + pm-quality-harness-loop. references/ retained as rubric/worker-scope provenance.

## What remains in this directory

- `references/` — `big-tech-rubric.md`, `worker-scopes.md`, `synthesis-matrix.md`, `ticket-schema.md`, `wiki-tree-harness.md`. Provenance for the quality cluster's rubric/worker-scope lineage; the live rubric SoT is `skills/quality-eval/`.
- `scripts/tmux-launcher.sh` — tmux 10-worker visible-pane launcher, retained verbatim. Not wired into any live skill; provenance only.

There is intentionally **no SKILL.md** here — this directory is not a discoverable skill. Routing for the jobs it used to cover:

| Job | Use instead |
|---|---|
| Codebase quality score + fix loop | `auto-pilot:adversarial-review-loop` (codebase mode) |
| Full quality → docs-sync → ship lifecycle | `auto-pilot:pm-quality-harness-loop` |
