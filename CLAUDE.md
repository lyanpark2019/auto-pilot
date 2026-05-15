# autopilot-swarm harness

## Project

autopilot-swarm is a Claude Code plugin orchestrating autonomous multi-agent development. One PM (claude-opus-4-7) dispatches tickets to 4–10 workers (opus/sonnet/haiku + codex) inside isolated git worktrees. Workers claim tickets atomically from a file-based bus under `.planning/autopilot/`, execute tasks via headless `claude -p` / `codex exec`, and commit diffs to isolated branches. The PM scores results via `quality-eval` skill and cherry-picks winners to main. See [README.md](README.md) and `.planning/autopilot/knowledge/synthesis.md` for architecture; `roadmap.json` for milestones.

## Layout

- `agents/` — agent specs (swarm-monitor, swarm-verifier)
- `scripts/` — PM loop, worker loop, session bootstrap/teardown
- `scripts/prompts/` — PM decision templates (8 .md files, envsubst-rendered)
- `skills/` — 6 Claude Code skills (swarm-init, swarm-bench, swarm-status, swarm-stop, swarm-ticket, autopilot-swarm)
- `.claude-plugin/` — plugin manifest (plugin.json)
- `.planning/autopilot/` — ticket bus, logs, knowledge, config, results (not git-tracked by default)

## Commands

| Script | Purpose |
|---|---|
| `scripts/start.sh` | Bootstrap tmux session, worktrees, message-bus dirs; validate config |
| `scripts/stop.sh` | Kill tmux session; optionally purge with `--purge` (worktrees + branches) |
| `scripts/run-pm.sh` | PM loop: bootstrap once, then explore → goal-decompose → score → ledger → dispatch (∞ until STOP) |
| `scripts/run-worker.sh` | Worker loop: atomic claim → headless execute → commit diff (runs per worker in tmux pane) |
| `scripts/bench.sh` | Three-arm benchmark: swarm vs claude-solo vs codex-solo; scores via quality-eval |

## Conventions

- **PM tickets live only in `.planning/autopilot/inbox/worker-N/`** — subdirs per worker, one .json per ticket (id.json).
- **Workers claim atomically via `mv` to `in_progress/`** — no two workers see same ticket. Worker wraps claim in trap to atomic-mv to `done/` or `outbox/` on exit.
- **Scope paths must not overlap across active tickets** — PM reads all in-flight `scope_paths`, rejects dispatch on conflict. Enforced in PM prompts + future strict check in run-pm.sh.
- **Every bash script must pass `bash -n`** — syntax validation gates all deployment. No hardcoded paths outside `.planning/autopilot/`.
- **Commits stay on `autopilot/worker-N` branches inside worktrees** — main is PM-only, never touched by workers. Worker branch = `../autopilot-swarm-worker-N/` relative to project root.
- **Honor `.planning/autopilot/STOP` sentinel file** — PM, workers, and bench scripts check for this file on each iteration loop and exit gracefully if present.

## Tooling Constraints

- **jq required** — all JSON parse/emit, no Python/node one-liners.
- **tmux required** — session management, pane isolation, no alternative.
- **No network installs** — everything vendored or pre-installed on host (tmux, jq, gettext/envsubst, bash, git, claude CLI, codex CLI).
- **Prefer Read/Edit/Write/Grep over Bash** — Claude Code tools for file I/O; Bash only for orchestration.
- **Use absolute paths inside `.planning/autopilot/`** — guarantees cross-worker safety; no pwd-relative paths for shared bus.

## When Stuck

- **Ticket bus + PM SOP** — `.planning/autopilot/knowledge/synthesis.md` (sections T1, T9); `roadmap.json` (milestones + success_criteria).
- **Specific decision rationale** — `topics.json` (each topic traces to ≥1 goal theme + source ref: external-web.md, external-obsidian.md, external-notebooklm.md).
- **Architecture + failure modes** — `synthesis.md` (10 themes + coverage table); `project-snapshot.md` (top 10 candidate improvements, directory sizes, test setup gaps).
- **User-facing onboarding** — [README.md](README.md) (quick start, roles, knowledge sources, file-bus structure, safety bounds, benchmark).
