# auto-pilot

Self-driving development loop for Claude Code. Opus 4.7 PM + Sonnet 4.6 (1M) parallel workers + Codex/Claude dual adversarial review + phase verify gates. Full auto, no confirms.

Built from `/insights` friction analysis on 381 sessions — every recurring failure mode is hardcoded as a guard.

## Install

```bash
# 1. clone (or symlink existing checkout into Claude plugins dir)
git clone <this-repo> ~/Documents/Project/auto-pilot
ln -s ~/Documents/Project/auto-pilot ~/.claude/plugins/auto-pilot

# 2. make hooks executable
chmod +x ~/Documents/Project/auto-pilot/hooks/*.sh

# 3. restart Claude Code session — plugin loads via SessionStart hook
```

## Usage

```
/auto-pilot start                   # use newest docs/specs/*.md
/auto-pilot start --spec PATH
/auto-pilot start --max-workers 6
/auto-pilot start --time-box 8h
/auto-pilot status
/auto-pilot resume
/auto-pilot stop
```

## Requirements

- Claude Code with Opus 4.7 access (PM session)
- Sonnet 4.6 1M-context tier (for workers via `Agent({model: "sonnet"})`)
- `codex` CLI on PATH (`brew install codex` or per Codex docs) — for adversarial reviewer
- A spec at `docs/specs/*-*.md` or `SPEC.md` with `## Phase N` headers
- A `CLAUDE.md` listing verify commands

## What it does

For each phase in the spec:

1. PM plans N non-overlapping work contracts
2. Dispatches N Sonnet 4.6 workers in 1 message (parallel) in isolated worktrees
3. Each worker edits, runs verify, reports diff
4. Dispatches 2N reviewers in 1 message (parallel): Codex adversarial + cold Claude
5. Both reviewers must APPROVE — either rejects → loop with finding
6. Runs project verify checklist (test+lint+typecheck+build)
7. Commits atomic per worker, pushes
8. Advances phase counter
9. Until last phase verify is green → SUCCESS report

## Hard stops

- Spec's last phase verify all green → SUCCESS, exit
- Same finding repeats 3 rounds → `pivot-needed`, exit (no whack-a-mole)
- Worker timeout > 20min → kill, exit
- User: `/auto-pilot stop`

## Friction guards (auto-loaded)

- Path typos (`Valut/`, `/tmp` cwd) — preflight warning
- Edits to `__init__.py` / composition roots — blocked (set `AUTO_PILOT_FORCE_COMPOSITION_ROOT=1` to bypass)
- `claude doctor` in non-interactive shell — blocked
- Chained Cloudflare SSL changes — blocked (one at a time)
- `ruff --fix` on composition roots — blocked
- Post-deploy: zombie port check, env placeholder leak check

## File layout

See `docs/architecture.md`.

## License

MIT
