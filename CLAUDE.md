# auto-pilot — repo guide

This is the auto-pilot plugin source. It is **a Claude Code plugin**, not application code. The plugin ships skills, agents, hooks, schemas, and a Python helper layer that the PM (Opus 4.7 main session) calls into.

> **Read first for full context:** [`docs/master-plan.md`](docs/master-plan.md) — purpose (brownfield skill-integration loop), skill-integration map, progress, roadmap. Loop design detail: [`docs/architecture.md`](docs/architecture.md).

## Publish identity

- **GitHub owner:** `lyanpark2019` (NOT Sewhoan, NOT fyqro)
- **Remote:** `git@github.com:lyanpark2019/auto-pilot.git`
- **gh CLI account:** active = `lyanpark2019` (verify with `gh auth status`)
- All `gh repo create`, `gh pr`, `gh release` operations for this repo must run under the `lyanpark2019` account. If the active gh account is anything else, switch first: `gh auth switch -u lyanpark2019`.

## Layout

- `.claude-plugin/{plugin,marketplace}.json` — manifest + standalone marketplace
- `skills/auto-pilot/SKILL.md` — entry skill (fires on `/auto-pilot`)
- `skills/` — bundled toolkit skills: setup-harness (+ its `scripts/`, `references/`, `templates/`, `evals/`), adversarial-review-loop, quality-eval, codebase-perfection-loop, doc-drift-audit, llm-wiki-architect, improve-codebase-architecture, diagnosing-{llm-output-leaks,stale-runtime}
- `commands/auto-pilot.md` — `/auto-pilot` slash command; `commands/harness-*.md` (8) — setup-harness commands
- `agents/` — PM, worker, codex-adversarial / claude-reviewer (legacy), `auto-pilot-{codex,claude}-reviewer.md` (PR3), tech-critic-lead, tdd-enforcer, security-reviewer, specialist-pool, `harness-{planner,generator,evaluator}.md` (setup-harness)
- `hooks/*.sh` + `hooks.json` — preflight, composition-root guard, bash guard, post-deploy, `pre-reviewer-write.sh` (PR3), guard-destructive, codex-conductor-guard (toolkit)
- `schemas/` — `contract|ticket|review.schema.json` (PR1, JSON Schema 2020-12)
- `scripts/` — `orchestrator.py`, `headless-loop.py`, plus PR1/PR2/PR3/PR4 modules listed below
- `docs/architecture.md` — loop + design (canonical)
- `docs/specs/` — PR-input specs (e.g. `2026-05-28-dogfood-smoke.md`)
- `docs/superpowers/{specs,plans}/` — design specs + implementation plans

## Python helper modules

| Module | Owner PR | Purpose |
|---|---|---|
| `scripts/_state.py` | PR4 | state.json TypedDict, `flock` lock, atomic temp+rename write |
| `scripts/_config.py` | base | `AutoPilotConfig` dataclass, env-driven defaults |
| `scripts/_log.py` | base | structured `event()` logger |
| `scripts/_prompts.py` | base | `prompts/*.md` loader |
| `scripts/_contract.py` | PR1 | schema validate, atomic write, flock, snapshot SHAs, PM-SIGNATURE |
| `scripts/_dispatch.py` | PR1 | ticket prep, diff freeze, `collect_round_outcome`, scope assert |
| `scripts/_subagent_helpers.py` | PR1 | ticket read, exit-code, done.marker, finding-hash |
| `scripts/_gc.py` | PR1 | bundle size cap, orphan ticket sweep |
| `scripts/_worktree.py` | PR2 | `WorktreeManager` (create / apply_to_main / cleanup / reap) |
| `scripts/_status.py` | PR2 | `WorkerStatus` enum + TERMINAL set |
| `scripts/_reviewer_wrapper.py` | PR3 | parallel reviewer dispatch with isolated env dicts |
| `scripts/_dogfood_gate.py` | PR4 | Tier 1 / Tier 2 acceptance assertions + CLI |
| `scripts/_budget.py` | PR5 | cost / token / pid caps for headless driver (extracted from `headless-loop.py`) |

## Editing this plugin

When changing agent contracts or hooks:
1. Edit the markdown / shell file
2. Re-run any active session (plugin discovery cache may persist for plugin subagents)
3. For hooks, `chmod +x` after creation

## Testing

```bash
# Full suite (199 tests, mypy + ruff clean)
python3 -m pytest tests/ -q
python3 -m mypy scripts/ hooks/
python3 -m ruff check scripts/ tests/ hooks/
python3 hooks/test_guard_destructive.py && python3 hooks/test_codex_conductor_guard.py  # bundled hook self-tests (script-style, not pytest)

# Smoke: orchestrator helper
python3 scripts/orchestrator.py init --spec docs/architecture.md --max-workers 4
python3 scripts/orchestrator.py status
python3 scripts/orchestrator.py stop

# Dogfood gate (no live claude session — assertions only)
./scripts/dogfood_tier1.sh --check
python3 scripts/_dogfood_gate.py --tier 1 --repo-root . --phases 2

# Hooks: feed sample JSON to stdin
echo '{"tool_input":{"file_path":"foo/__init__.py"}}' | hooks/pre-edit-composition-root.sh
# should exit 2 and print "BLOCKED"

echo '{"tool_input":{"command":"claude doctor"}}' | hooks/pre-bash-guard.sh
# should exit 2 and print "BLOCKED"

# PR3 reviewer-write guard (requires AUTO_PILOT_SUBAGENT_ROLE + AUTO_PILOT_OUTPUT_DIR)
AUTO_PILOT_SUBAGENT_ROLE=codex-reviewer AUTO_PILOT_OUTPUT_DIR=/tmp/ok \
  echo '{"tool_name":"Edit","tool_input":{"file_path":"/etc/passwd"}}' | hooks/pre-reviewer-write.sh
# should exit 2 and print "BLOCKED"
```

## Rules for this plugin's own development

- Files ≤500 lines — enforced in CI by `scripts/quality/check-module-size.sh`; documented exceptions in `scripts/quality/module_size_budget.txt` (`<path>|<max_lines>`, reason in a comment). Scope: tracked `*.py`/`*.sh` (excl `docs/`) + every `SKILL.md`.
- Type hints required; docstrings on public API only.
- No code comments narrating WHAT — agent markdown explains WHY.
- Hooks are non-blocking by default (exit 0). Explicit guards exit 2 with `BLOCKED` message on stderr.
- All hook scripts must read tool input from stdin as JSON.
- Skill/command markdown must specify `${CLAUDE_PLUGIN_ROOT}` for any plugin-internal path.
- `state.json` writes must go through `_state.save_state` (lock + atomic); never write the file directly.
- `$ROOT` mutations must go through `WorktreeManager.apply_to_main` (PR2 invariant) — outside of that path, only `stash_if_dirty` is allowed to touch the main tree.

## Shell & environment (host = macOS, zsh login shell)

These bit real sessions — encode them, don't relearn them:

- **Bundled `.sh` are shellchecked in CI** (`shellcheck hooks/*.sh` + `find skills -name '*.sh' | shellcheck -S warning`, pinned 0.11.0). Keep new scripts at 0 warnings: `cd X || exit`, quote vars, `find -print0 | xargs -0` (not `find | xargs`), no `ls | grep`, split `local x; x=$(...)`.
- **zsh does NOT word-split unquoted `$VAR`** — `for s in $LIST` iterates ONCE with the whole string. In any ad-hoc loop over a space-separated list, wrap in `bash <<'EOF' … EOF` or use an explicit array. (This silently no-op'd a multi-dir delete in a prior session.)
- **macOS = bash 3.2 + BSD tools.** No `mapfile`/`readarray`; `sed -i` needs `sed -i ''`; BSD `sed`/`grep` differ from GNU. Prefer a Python one-liner over a clever `sed` for cross-platform edits.
- **Non-interactive Codex/CLI subagents must consume stdin** — feed a prompt (`--prompt-file - < file` / heredoc / inline arg) or redirect `< /dev/null`. A bare `codex exec` inherits the TTY and hangs. (auto-pilot's reviewers already do this; applies to any new codex call.)
