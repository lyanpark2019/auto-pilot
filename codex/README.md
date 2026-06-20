# codex/ — versioned Codex CLI skills

**This repo is the source of truth** for the Codex CLI skills below. They are forks
imported from `~/.codex/skills/`; from now on the flow is one-way:

1. Edit the skill **here** (`codex/skills/<name>/`).
2. Deploy: `./sync-to-codex.sh` (from this directory).
3. Verify: `./sync-to-codex.sh -d` reports repo↔deployed drift (exit 1 if any).

Never hand-edit `~/.codex/skills/<name>/` for a managed skill — the next sync
overwrites it. If a hotfix landed there anyway, port it back into the repo first
(`-d` shows exactly what differs), then sync.

## Managed skills (11)

| Skill | Purpose |
|---|---|
| `diagnose` | Disciplined diagnosis loop for hard bugs and perf regressions: reproduce → minimize → hypothesize → instrument → fix → regression-test. |
| `grill-with-docs` | Stress-test a plan against the repo's domain model, `CONTEXT.md`, and ADRs; sharpen terminology and update domain/decision docs inline. |
| `handoff` | Compact the current conversation into a handoff document so a fresh agent or session can continue the work. |
| `improve-codebase-architecture` | Find evidence-backed deepening opportunities: module boundaries, interface simplification, refactor planning via domain language + ADRs. |
| `migrate-to-codex` | Migrate supported Claude Code instruction files, skills, agents, and MCP config into Codex project and global files. |
| `prototype` | Build throwaway prototypes (terminal, state-machine, business-logic probes, UI variations) to explore a design before production code. |
| `tdd` | Test-driven development: red-green-refactor, one vertical behavior slice at a time (one failing test → minimal code → pass → repeat). |
| `to-issues` | Slice a plan, spec, PRD, or conversation into independently grabbable GitHub or local issue tickets (vertical, shippable slices). |
| `to-prd` | Turn the current conversation or a rough idea into a concise PRD, optionally submitted as a GitHub issue. |
| `triage` | Issue triage through a disciplined state machine: sort bugs/requests/backlogs into reproducible, actionable, labeled, routed work. |
| `zoom-out` | Give broader context on an unfamiliar code area, plan, or decision — connect local details to system architecture before acting. |

## Sync semantics (`sync-to-codex.sh`)

- One-way rsync, **per skill dir**: `codex/skills/<name>/` → `~/.codex/skills/<name>/`.
- `--delete` applies **inside each managed skill dir only** — files removed from the
  repo disappear from the deployed copy.
- The destination **parent is never pruned**: unmanaged skills and symlinks living in
  `~/.codex/skills/` are untouched.
- `__pycache__/`, `*.pyc`, `.DS_Store` are never shipped (they are gitignored here too).
- Flags: `--dry-run` (show plan, write nothing) · `-d`/`--diff` (drift report, exit 1
  on drift) · `-h` (help). Destination overridable via `CODEX_SKILLS_DIR`.
- Pre-flight refuses to run if any skill dir lacks a `SKILL.md`.

## Notes

- `migrate-to-codex` carries its upstream Apache-2.0 license (`LICENSE.txt`); the
  other ten carry an upstream attribution file (`LICENSE-upstream.txt`). Keep these
  files when editing.
