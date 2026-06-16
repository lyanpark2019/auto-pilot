# auto-pilot — repo guide

This is the auto-pilot plugin source. It is **a Claude Code plugin**, not application code. The plugin ships skills, agents, hooks, schemas, and a Python helper layer that the PM (the main session) calls into.

> **Read first for full context:** [`docs/onboarding/README.md`](docs/onboarding/README.md) — AI/developer start path, graphify commands, task routing. Then [`docs/master-plan.md`](docs/master-plan.md) for roadmap and [`docs/architecture.md`](docs/architecture.md) for loop design detail.

## Code questions = vault-first

Read the curated vault page first — answers usually live there (human-verified, fact-checked). Order:
- **① Obsidian vault**: `~/Documents/Knowledge/wiki/projects/auto-pilot/` (curated pages: `architecture.md`, `master-plan.md`, `index.md`, `graphify/`, …)
- **② repo docs**: this repo's `docs/` + folder-level `CLAUDE.md`
- **③ graphify supplement**: `graphify query/explain/path/affected` over `graphify-out/graph.json` — only for symbols/edges/freshness the vault doesn't cover (use the code-only filtered graph; SQL not indexed). No grep-guessing before ①–②.

Global Hard Rule "Discovery order = vault-first" is the SoT; this block just pins this repo's vault path.

## Principles (Nisi 2026-06)

- **Prompts/specs are the durable re-runnable asset; code is the output** ("code is sawdust") — invest in the spec, not in patching generated artifacts.
- **Enforce with code, not prompts** — invariants live in hooks, schemas, and state machines; prose explains, it does not enforce.
- **Evidence over trust** — verify claims carry a persisted log + SHA-256 (`shasum -a 256`); reviewers recompute the hash, mismatch = REJECT.
- **Skills = Gotchas-first, ≤500 lines** — guide around landmines instead of re-teaching coding; bulk goes to `references/`.
- **Failures are harness bugs** — fix the system (hook, schema, gate, agent contract), not the one bad output.
- **Measure with evals before believing** — a change "helps" only after the `evals/` harness says so, not because it reads well.

## Publish identity

- **GitHub owner:** `lyanpark2019` (NOT Sewhoan, NOT fyqro)
- **Remote:** `git@github.com:lyanpark2019/auto-pilot.git`
- **gh CLI account:** active = `lyanpark2019` (verify with `gh auth status`)
- All `gh repo create`, `gh pr`, `gh release` operations for this repo must run under the `lyanpark2019` account. If the active gh account is anything else, switch first: `gh auth switch -u lyanpark2019`.
- **Deploy identity assertion (mandatory, every push/release/run-watch):** the active account flip-flops mid-session (concurrent sessions share the host-global keyring — observed Sewhoan and MoneyPick-KO re-switching it within minutes). A switch at session start is NOT sufficient. Immediately before EVERY `git push` / `gh release` / `gh run` command, verify and switch in the same shell invocation:
  ```bash
  ACTIVE=$(gh api user --jq .login); [ "$ACTIVE" = "lyanpark2019" ] || gh auth switch --hostname github.com --user lyanpark2019
  ```
  Never assume a previous command's switch is still in effect.
- Actions run-history pruning: `bash scripts/ci/prune_action_runs.sh --keep 4 --apply` (dry-run without `--apply`; refuses to run under any account but `lyanpark2019`).

## Layout

- `.claude-plugin/{plugin,marketplace}.json` — manifest + standalone marketplace; `.mcp.json` — bundled MCP server config
- `skills/auto-pilot/SKILL.md` — entry skill (fires on `/auto-pilot`)
- `skills/` — 11 dirs / 11 active: setup-harness (+ its `scripts/`, `references/`, `templates/`, `evals/`; loop scoring delegates to ARL codebase mode), adversarial-review-loop (branch/codebase/multi-agent + `--lifecycle` mode — absorbed pm-quality-harness-loop 2026-06-07), quality-eval (rubric SoT, data not entry point), residue-audit, codex-orchestra, sha-deploy-standard, swarm (subcommand-routed: init/start/status/stop/ticket/bench — absorbed swarm-bench 2026-06-07), doc-management (the docs subsystem — REBUILD/MAINTAIN/AUDIT modes; absorbs the retired graphify-doc-rebuild / doc-drift-audit / doc-sync / llm-wiki-architect skills), improve-codebase-architecture (Matt Pocock MIT fork, LICENSE-upstream.txt), diagnosing (llm-output-leaks + stale-runtime modes, merged 2026-06-07)
- `commands/` — 7 slash commands: `auto-pilot-server`, `vault-{build,score,dashboard,selftest}` (4), `setup-claude-md`, `sha-deploy-init`. `/auto-pilot` routes via the skill — the same-name command file was folded into `skills/auto-pilot/SKILL.md` 2026-06-07 (commands+skills share one registry namespace; the pair double-registered). eval-run absorbed as `/auto-pilot eval`; harness + harness-ops deleted 2026-06-07
- `agents/` — 18 contracts: core loop (pm-orchestrator, worker, retro), review (`auto-pilot-{codex,claude}-reviewer.md` hardened pair — legacy codex-adversarial/claude-reviewer deleted 2026-06-07, tech-critic-lead, review-gatekeeper (tdd-enforcer + security-reviewer merged 2026-06-07), specialist-pool; code-perfector retired 2026-06-07 → residue-audit/ARL), swarm-{explorer,monitor,verifier}, vault set (vault-pm-orchestrator + vault-{edge-curator,graph-enricher,knowledge-author,structure-curator} — the 4 merged 2026-06 round-2, 25 legacy vault agents removed; harness-{planner,generator,evaluator} deleted 2026-06-07 — 1:1 duplicate of auto-pilot loop) + enrichment-fetcher (inc2 Phase 2b live MCP-fetch producer) + escalation-resolver (inc3 Phase 2 tier-2 bounded retry agent); shared review substance lives in `skills/adversarial-review-loop/references/review-core.md`; goal-{scout,judge,worker} live in global `~/.claude/agents/` (not bundled)
- `hooks/*.sh|*.py` + `hooks.json` — preflight, composition-root guard, bash guard, post-deploy, `pre-reviewer-write.sh` (PR3), guard-destructive, codex-conductor-guard, `doc-sync-update.sh` (merged graph-freshness watcher: code graph stale-flag + vault raw/sources .md eager graphify update), `notebooklm_delete_gate.sh` (confirm-gated deletes, Bash + MCP shapes), `pm_final_report.sh`, + 7 round-2 enforcement hooks (`pre-edit-human-only`, `branch-lock`, `deletion-diff-guard`, `gh-auth-preflight`, `ruff-import-integrity`, `dispatch-contract-gate`, `creation-gate`) + round-3 additions (`context-watch`, `artifact-ledger`, `subagent-deliverable-check` — SubagentStop advisory) + `learning-miner-stop` (Stop hook: advisory improvement-ticket ledger accumulation on auto-pilot runs) + `worker-scope-gate` (PreToolUse Edit/Write: denies worker edits outside `AUTO_PILOT_SCOPE_FILES`; inert until a dispatch path sets the env) + `headless-sync-dispatch-guard` (PreToolUse Task|Bash: denies `run_in_background` under `HARNESS_HEADLESS=1` — F-6 orphan-dispatch guard) + `verifier-tier-gate` (PreToolUse Task: denies verifier dispatch with under-tier `model:` override per `skills/auto-pilot/references/model-routing.yaml`) + `shellcheck-on-write` (PostToolUse Write|Edit|MultiEdit: advisory — runs shellcheck -S warning on any *.sh written/edited, never blocks) + `state-write-guard` (PreToolUse Edit/Write + Bash: denies direct state.json edits and git am/apply/format-patch outside apply_to_main; active for worker, codex/claude-reviewer, review-gatekeeper, and tech-critic-lead roles (per AUTO_PILOT_SUBAGENT_ROLE; unset/unknown role → no-op)) + `session-distill-stop` (Stop hook: advisory deterministic session-record stub into vault sessions/; provenance capture only — distillation delegated to retro/miner) + `_stdin_contract.py` (shared stdin-JSON contract validator — fail-open `read_tool_input`/`full_payload_or_none` helpers consumed by Python hooks) — full wiring SoT = `hooks/hooks.json` (28 scripts)
- `schemas/` — `contract|ticket|review.schema.json` (PR1) + `improvement-ticket.schema.json` (improvement-ticket loop), `preflight.schema.json`, `prompt-fixture.schema.json`, `routing-ledger.schema.json` (role×model routing ledger), `enrichment-evidence.schema.json` (increment-2 enrich gate), `escalation-record.schema.json` (increment-2 Phase-3 escalation) (9 files, JSON Schema 2020-12); swarm's ticket/score/verify/plugin schemas live in `swarm/schemas/`
- `scripts/` — `orchestrator.py`, `headless-loop.py`, the helper modules listed below (PR1-PR5 plus later waves: discovery, routing, evidence, risk, improvement-ticket loop), `build_dashboard_data.py`, `quality/` gates, `scripts/docs/` doc-CI guards (`check_doc_reference_integrity.py` file:line citation guard, `check_asset_counts.py`, `check_codex_provenance.py`, `mirror_docs.py`), `scripts/evals/` (eval-harness runner: `cli`/`runner`/`aggregate`/`regress`/`stats`/`oracle_api`/`_types`)
- `vault/` — export layer (vault-builder absorbed): `pipeline/`, `sources/`, `scripts/`, `rubrics/`, `templates/`, `dashboard/`, `tests/`
- `swarm/` — parallel execution backend: `scripts/`, `schemas/`, `tests/`, `docs/`
- `codex/` — 12 codex skill forks under `codex/skills/` (repo = SoT) + `sync-to-codex.sh` + `README.md`; provenance SoT: `codex/UPSTREAM.md`
- `deploy/` — sha-deploy templates (`deploy/templates/`)
- `dashboard/` — scorecard dashboard
- `evals/` — eval harness
- `docs/architecture.md` — loop + design (canonical)
- `docs/specs/` — active PR-input / dogfood specs under `docs/specs/`; shipped plan/spec docs get distilled into `docs/architecture.md` then deleted (disposal step owned by `agents/retro.md`)

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
| `scripts/_discovery.py` | Step 1+2 | graphify provenance record, diff-relevance freshness check (`orchestrator.py discover`), `resolve_report` bundle seam |
| `scripts/risk_assess.py` | v0.7.1 | diff → risk tier + `review_policy` JSON (advisory gate for review dispatch; SoT for tier/policy tokens) |
| `scripts/_routing.py` | A+B | model-routing.yaml resolver: codex effort by risk tier, verifier tier floor, verifier agent list |
| `scripts/_heartbeat.py` | A+B | reviewer status.json beats + review-status table renderer |
| `scripts/codex_review_bounded.py` | A+B | bounded codex exec: tiered effort → timeout → retry → ABSTAIN |
| `scripts/_round_budget.py` | A+B | round-budget findings loaders + CLI handler (`cmd_round_budget`, `_emit_hard_stop`, `register_cli_subparsers`) extracted from orchestrator.py |
| `scripts/_evidence.py` | run-3 | review-round evidence exit gate; claude APPROVE + codex APPROVE-or-honest-ABSTAIN |
| `scripts/_improvement.py` | improvement-ticket loop | improvement-ticket identity + durable ledger I/O for the miner |
| `scripts/_promotion.py` | improvement-ticket loop | ticket FSM + Phase-1 promotion gate evaluation |
| `scripts/learning_miner.py` | improvement-ticket loop | scan reviewer findings + doom-loop signals → bump ticket counters (CLI via hooks/learning-miner-stop.sh) |
| `scripts/_ledger.py` | A+B | routing-ledger IO, schema validation, record derivation |
| `scripts/_rebalance.py` | A+B | pure rebalance rule engine for the routing ledger |
| `scripts/_contract_check.py` | run-3 | producer/validator for dispatch `contract-check.json` artifacts |
| `scripts/_recover.py` | run-3 | crash-recovery helpers for the loop (am-state cleanup, reap) |
| `scripts/asset_registry_check.py` | creation-gate | registry overlap checker; emits artifact consumed by hooks/creation-gate.sh |
| `scripts/_learnings.py` | improvement-ticket loop | injection resolver: select + render gate-passed tickets for dispatch bundle; `is_gate_passed` shared predicate; `AUTO_PILOT_DISABLE_LEARNINGS` env var disables injection (kill-switch / no-inject arm for `evals/cases/learnings-ab/`) |
| `scripts/_mirror_learnings.py` | improvement-ticket loop | promotable-ticket → vault gotcha mirror (derived, idempotent one-way sync); `orchestrator.py improvements-mirror` subcommand |
| `scripts/measure_learnings_injection.py` | improvement-ticket loop | Phase-4 injection-recall + gate-vs-ungated A/B (`--compare-gating`): what the gate filters out vs what leaks in without it; `orchestrator.py measure-injection [--compare-gating]` subcommand |
| `scripts/_enrich_gate.py` | inc2-enrich | deterministic enrichment gate (source-tier floor + sha-verified evidence; LLM-judge advisory only) |
| `scripts/_enrich_persist.py` | inc2-enrich | gate-and-persist admitted candidates → vault enrichment/ pages (upsert by sha, additive); `orchestrator.py enrich` subcommand |
| `scripts/_enrich_fetch.py` | inc2-enrich | live-fetch shaping seam: Fetcher Protocol (MCP boundary) + shape_hit (sha-computing) + fetch_and_persist; agent owns live MCP I/O |
| `scripts/_escalation.py` | inc2-Phase3 | escalation-record identity + durable ledger I/O: fingerprint, bump_or_create RMW, drive_enrich seam, CLI (escalation-record/list/enrich); + record_resolution writer (resolved/abandoned) + orchestrator.py escalation-resolve subcommand (inc3 Phase 2) |
| `scripts/_escalation_emit.py` | inc3-escalation | best-effort tier-1->tier-2 boundary emit; wraps _escalation.bump_or_create at the 3 give-up points, never raises (additive) |
| `scripts/measure_enrich_precision.py` | inc2-enrich | gate-precision measure: admit/reject rate + per-tier + reason-histogram over candidate JSONs (re-runs _enrich_gate.evaluate); CLI measure-enrich |
| `scripts/measure_escalation.py` | inc3-Phase3 | deterministic escalation-ledger metrics: by_state + by_problem_class + resolution/recovery rates + enrich-pages-written (re-runs over the ledger); `orchestrator.py measure-escalation` |

## Editing this plugin

When changing agent contracts or hooks:
1. Edit the markdown / shell file
2. Re-run any active session (plugin discovery cache may persist for plugin subagents)
3. For hooks, `chmod +x` after creation

## Testing

```bash
# Full suite (count = whatever pytest collects — do not hardcode; mypy + ruff clean)
python3 -m pytest tests/ -q
python3 -m mypy scripts/ hooks/
python3 -m ruff check scripts/ tests/ hooks/
python3 hooks/test_guard_destructive.py && python3 hooks/test_codex_conductor_guard.py && python3 hooks/test_notebooklm_delete_gate.py && python3 hooks/test_dispatch_contract_gate.py && python3 hooks/test_headless_sync_dispatch_guard.py && python3 hooks/test_verifier_tier_gate.py && python3 hooks/test_pre_edit_human_only.py && python3 hooks/test_preflight_handoff.py && python3 hooks/test_subagent_deliverable_check.py && python3 hooks/test_doc_sync_update.py && python3 hooks/test_session_distill_stop.py  # bundled hook self-tests (script-style, not pytest)

# vault export-layer suite
( cd vault && python3 -m pytest tests/ -q )

# bats: auto-pilot snippet pins + ARL helpers + setup-harness hooks/CLI (do not duplicate collected counts here)
( cd skills/auto-pilot && bats tests/ )
( cd skills/adversarial-review-loop && bats tests/ )
( cd skills/setup-harness && bats tests/ )

# module-size gate (≤500 lines, exceptions in scripts/quality/module_size_budget.txt)
bash scripts/quality/check-module-size.sh

# doc citation integrity (file:line in docs/ + CLAUDE.md resolve; CI-wired)
python3 scripts/docs/check_doc_reference_integrity.py

# graphify Obsidian vault loop: rerun query regression, compact symbol notes, validate links/canvas/counts
python3 scripts/graphify_vault_loop.py --vault /Users/lyan/Documents/Knowledge/wiki/projects/auto-pilot --compact --max-iterations 2

# Smoke: orchestrator helper
python3 scripts/orchestrator.py init --spec docs/architecture.md --max-workers 4
python3 scripts/orchestrator.py status
python3 scripts/orchestrator.py stop

# Dogfood gate (no live claude session — assertions only)
./scripts/dogfood_tier1.sh --check
python3 scripts/_dogfood_gate.py --tier 1 --repo-root . --phases 2

# Hooks: feed sample JSON to stdin
# composition-root guard fires only on an EXISTING, non-trivial root (new/empty __init__.py passes)
mkdir -p /tmp/cr-pkg && printf 'from .x import Y\n' > /tmp/cr-pkg/__init__.py
echo '{"tool_input":{"file_path":"/tmp/cr-pkg/__init__.py"}}' | hooks/pre-edit-composition-root.sh  # populated → exit 2 "BLOCKED"
echo '{"tool_input":{"file_path":"foo/__init__.py"}}' | hooks/pre-edit-composition-root.sh           # not-yet-created → exit 0 (no content to corrupt)

echo '{"tool_input":{"command":"claude doctor"}}' | hooks/pre-bash-guard.sh
# should exit 2 and print "BLOCKED"

# PR3 reviewer-write guard (requires AUTO_PILOT_SUBAGENT_ROLE + AUTO_PILOT_OUTPUT_DIR)
AUTO_PILOT_SUBAGENT_ROLE=codex-reviewer AUTO_PILOT_OUTPUT_DIR=/tmp/ok \
  echo '{"tool_name":"Edit","tool_input":{"file_path":"/etc/passwd"}}' | hooks/pre-reviewer-write.sh
# should exit 2 and print "BLOCKED"
```

## Commit trailers — decision capture (adapted from oh-my-claudecode, 2026-06-07)

Non-trivial commits append structured trailers so the WHY and rejected alternatives
survive context compaction in git history:

```
Rejected: <alternative> | <reason>
Constraint: <what bounded the design>
Not-tested: <path/case left unverified>
Confidence: <high|medium|low>
```

`Not-tested:` is mandatory whenever verify did not cover every changed path —
aligns with the 보수적·냉정 rule (residual risk stated, not hidden). Trivial
commits (typo, regen) skip trailers.

## Rules for this plugin's own development

- Files ≤500 lines — enforced in CI by `scripts/quality/check-module-size.sh`; documented exceptions in `scripts/quality/module_size_budget.txt` (`<path>|<max_lines>`, reason in a comment). Scope: tracked `*.py`/`*.sh` (excl `docs/`) + every `SKILL.md`.
- Type hints required; docstrings on public API only.
- No code comments narrating WHAT — agent markdown explains WHY.
- Hooks are non-blocking by default (exit 0). Explicit guards exit 2 with `BLOCKED` message on stderr.
- All hook scripts must read tool input from stdin as JSON.
- Skill/command markdown must specify `${CLAUDE_PLUGIN_ROOT}` for any plugin-internal path.
- `state.json` writes must go through `_state.save_state` (lock + atomic); never write the file directly. CODE-ENFORCED by `hooks/state-write-guard.sh` (Edit/Write deny for worker, codex/claude-reviewer, review-gatekeeper, tech-critic-lead roles).
- `$ROOT` mutations must go through `WorktreeManager.apply_to_main` (PR2 invariant) — outside of that path, only `stash_if_dirty` is allowed to touch the main tree. CODE-ENFORCED by `hooks/state-write-guard.sh` (Bash git am/apply/format-patch deny for worker, codex/claude-reviewer, review-gatekeeper, tech-critic-lead roles).

## Shell & environment (host = macOS, zsh login shell)

These bit real sessions — encode them, don't relearn them:

- **Bundled `.sh` are shellchecked in CI** (`shellcheck hooks/*.sh` + `find skills -name '*.sh' | shellcheck -S warning`, pinned 0.11.0). Keep new scripts at 0 warnings: `cd X || exit`, quote vars, `find -print0 | xargs -0` (not `find | xargs`), no `ls | grep`, split `local x; x=$(...)`.
- **zsh does NOT word-split unquoted `$VAR`** — `for s in $LIST` iterates ONCE with the whole string. In any ad-hoc loop over a space-separated list, wrap in `bash <<'EOF' … EOF` or use an explicit array. (This silently no-op'd a multi-dir delete in a prior session.)
- **macOS = bash 3.2 + BSD tools.** No `mapfile`/`readarray`; `sed -i` needs `sed -i ''`; BSD `sed`/`grep` differ from GNU. Prefer a Python one-liner over a clever `sed` for cross-platform edits.
- **Non-interactive Codex/CLI subagents must consume stdin** — feed a prompt (`--prompt-file - < file` / heredoc / inline arg) or redirect `< /dev/null`. A bare `codex exec` inherits the TTY and hangs. (auto-pilot's reviewers already do this; applies to any new codex call.)
- **Parallel/concurrent work → dedicated worktree, never the shared main checkout.** Two sessions sharing one working tree → a `git checkout` in one flips the shared `.git/HEAD`, so the other's commit is DENIED by branch-lock (the tree really IS on main then) and uncommitted work can be clobbered. One-command form: `scripts/ap-worktree.sh new <slug>` (worktree off latest main on `fix/<slug>-<date>`), then drive ALL git through `git -C <wt>` (resolves the worktree branch, not the flipped root HEAD; push with an explicit feature refspec → gates on dst, passes with no bypass), and `scripts/ap-worktree.sh done <slug>` / `prune` to clean up. PR/commit bodies via `-F file` / `--body-file` — inline git/push/main prose trips branch-lock's command scan.
