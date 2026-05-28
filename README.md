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
/auto-pilot start                   # use newest docs/specs/*.md (interactive, one phase per turn)
/auto-pilot start --spec PATH
/auto-pilot start --max-workers 6
/auto-pilot status
/auto-pilot resume
/auto-pilot stop

# True headless infinite loop (this is the "one-click autonomous" you want):
/auto-pilot-server                  # spawn Python driver in background
# or directly:
python3 ~/.claude/plugins/auto-pilot/scripts/headless-loop.py \
  --max-iter 100 --sleep 10 \
  --max-cost-usd 50 --max-tokens 50000000 --max-concurrent-claude 4
python3 ~/.claude/plugins/auto-pilot/scripts/headless-loop.py --once   # smoke test

# Dogfood smoke harness (PR4) — runs the 2-phase smoke spec end-to-end:
./scripts/dogfood_tier1.sh          # PR1+PR2 surface only (reviewers fall back)
./scripts/dogfood_tier2.sh          # full PR3 reviewer sandbox
./scripts/dogfood_tier1.sh --check  # gate assertions only, no loop spawn
```

## Requirements

- Claude Code with Opus 4.7 access (PM session)
- Sonnet 4.6 1M-context tier (for workers via `Agent({model: "sonnet"})`)
- `codex` CLI on PATH (`brew install codex` or per Codex docs) — for adversarial reviewer
- A spec at `docs/specs/*-*.md` or `SPEC.md` with `## Phase N` headers
- A `CLAUDE.md` listing verify commands

## What it does

For each phase in the spec:

1. **Tech-critic gate** — `tech-critic-lead` rejects scope-creep contracts BEFORE workers touch code ("기능은 비용", from cc-system)
2. PM plans N non-overlapping work contracts
3. Dispatches N Sonnet 4.6 workers in 1 message (parallel) in isolated worktrees
4. Each worker edits, runs verify, reports diff
5. Dispatches reviewers in 1 message (parallel):
   - `codex-adversarial` (always)
   - `claude-reviewer` cold (always)
   - `tdd-enforcer` if runtime code touched (deletes impl written before tests, from Superpowers)
   - `security-reviewer` if trust-boundary files touched
   - Other specialists per `agents/specialist-pool.md`
6. ALL reviewers must APPROVE — any REJECT → loop with finding
7. Hard gates inside review: scope-drift (out-of-contract files), scope-reduction (worker loosened test instead of fixing impl)
8. Runs project verify checklist (test+lint+typecheck+build)
9. Commits atomic per worker with trailers (`auto-pilot-iter`, `auto-pilot-phase`, `auto-pilot-contract`)
10. Advances phase counter
11. Until last phase verify is green → SUCCESS report

### Headless mode (true autonomous)

`/auto-pilot-server` (or `python3 scripts/headless-loop.py`) runs an outer driver that:
1. Snapshots HEAD pre-phase
2. Checks budget caps (`--max-cost-usd`, `--max-tokens`, `--max-concurrent-claude` via `pgrep`) — abort with status `cost-cap` if exceeded
3. Spawns `claude -p --dangerously-skip-permissions` with `HARNESS_HEADLESS=1` and the auto-pilot skill
4. On phase exit:
   - success → next iteration
   - timeout / fail → `git stash` any dirty $ROOT edits under `auto-pilot-iter-N-{timeout,failed}` (recoverable, not destructive); per-worktree cleanup handles in-flight work
5. Accumulates parsed cost + token totals into `state.json` for cap enforcement
6. Repeats until terminal status (`success`, `failed`, `pivot-needed`, `stopped`, `cost-cap`) or `--max-iter`

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
- Over-scoped contracts — `tech-critic-lead` rejects with reason
- Implementation without tests — `tdd-enforcer` REJECTs
- Out-of-scope edits — claude-reviewer + codex-adversarial REJECT on scope drift
- Reviewer writes outside `outputs/<role>/` — `hooks/pre-reviewer-write.sh` blocks (PR3)
- Phase fail leaves dirty tree — `headless-loop.py` `stash_if_dirty` (PR4 replaces destructive reset)
- Run-away cost or fork-bomb — `--max-cost-usd` / `--max-tokens` / `--max-concurrent-claude` (PR4)
- `state.json` concurrent writes — flock + atomic temp+rename (PR4)
- Spec parser `## Phase` inside code fences — ignored by `_count_phases` (PR4)

## Inspired by

- [greatSumini/cc-system](https://github.com/greatSumini/cc-system) — `run-server.py` infinite loop pattern, `tech-critic-lead`, HARNESS_HEADLESS env signal, iter-id commit trailers, rollback on fail
- [obra/superpowers](https://github.com/obra/superpowers) — 7-phase template, TDD-first hard rule (deletes pre-test code)
- [everything-claude-code](https://github.com/JonathanRosenberg/everything-claude-code) — specialist agent pool (security/database/tdd-guide/etc.)
- [LiorCohen/sdd](https://github.com/LiorCohen/sdd) — Spec-driven development phasing
- Lessons from `/insights` (381 sessions over 14 days) — every friction class is a guard

## File layout

See `docs/architecture.md`.

## License

MIT
