---
type: generated-mirror
topic: auto-pilot docs map
source_commit: 128e95ba77c0867913d5db48c739e2c39da120b3
manual_edit: false
---

# auto-pilot docs

This directory is the source-of-truth map for humans and AI agents working on the auto-pilot plugin.

## Start here

| Reader | First stop | Then read |
|---|---|---|
| Developer | `docs/onboarding/README.md` | `docs/architecture.md`, `docs/asset-charter.md`, then task-specific docs |
| AI agent | `docs/onboarding/README.md` | `skills/auto-pilot/references/project-context-resolution.md`, graphify query results, then source |
| Release / CI maintainer | `CLAUDE.md` | `docs/perf-budget.md`, `.github/workflows/ci.yml` |
| Plugin asset editor | `docs/asset-charter.md` | matching `skills/`, `agents/`, `commands/`, `hooks/`, or `schemas/` file |

## Source-of-truth order

1. **Current code and generated graph** for `What`: run graphify before guessing.
2. **Architecture and asset docs** for intended ownership and routing.
3. **Historical docs and specs** for `Why`: preserve rationale, but do not treat old facts as current without source verification.
4. **Raw source read** for final claim verification before editing docs or behavior.

## Docs map

- `docs/onboarding/README.md` — AI / Developer onboarding hub.
- `docs/architecture.md` — canonical architecture and loop design.
- `docs/asset-charter.md` — asset ownership, retention, and retired-name decisions.
- `docs/master-plan.md` — roadmap and current consolidation plan.
- `docs/perf-budget.md` — performance budgets and benchmark gates.
- `docs/prompt-quality.md` — prompt fixture schema, LLM-call sanitizer, and budget gates.
- `docs/configuration.md` — env vars, bounded defaults, and config verification.
- `docs/7-phase-template.md` — phase-spec template for autonomous work.
- `docs/specs/` — active dogfood/spec inputs.
- `docs/history/` — distilled changelogs; historical, not current implementation truth.
- `docs/plans/` — approved implementation/design plans; active while a branch is in flight, historical after the result is distilled.

## Doc freshness rule

For code facts, use `graphify update . --force`, `graphify query`, `graphify explain`, `graphify path`, or `graphify affected` first. Then read the source files surfaced by the graph. Only after that should prose be changed.
