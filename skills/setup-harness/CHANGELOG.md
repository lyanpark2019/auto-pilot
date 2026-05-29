# Changelog

## 2.1.0 — 2026-05-25

### Added
- **Folder-level CLAUDE.md automation** (`scripts/folder-claudemd.sh`): detects dense/layer
  candidate folders (≥`FOLDER_THRESHOLD`=10 source files) and scaffolds ≤10-line local
  interfaces. Wired into `bootstrap.sh` and `harness-loop.sh` (claudemd autofix). Previously
  folder-level interfaces were doc-only (Step 2 described them; nothing generated them).
- **`scripts/stop-e2e.sh`**: Playwright CLI smoke Stop hook. Resolves a dangling reference —
  the Stack→Hook table pointed to it but it was never shipped. `bootstrap.sh` now **auto-registers**
  it as a Stop hook when it detects a Playwright dep in `package.json` (`STACK_BROWSER`), tuple-deduped
  so re-runs never double it; non-browser projects skip it. `verify-harness.sh` [C3] proves it
  no-ops safely (respects `stop_hook_active`, exits 0 without `package.json`).

### Changed
- **Folder-level coverage is its own score dimension** (`folder_interfaces`), not a blend into
  `claudemd`. Scorer now has 15 dimensions (was 14). `claudemd` measures the root file alone, so
  a project with a strong root no longer silently drops 100→70 on re-score (the previous blend
  conflated two concerns). `folder_interfaces` = substantive folder coverage; no candidate folders
  (or `FOLDER_THRESHOLD` raised to opt out) → 100, so small projects are never penalized.
  Coverage counts a folder only when its CLAUDE.md is substantive (scaffold `{placeholder}` tokens
  replaced) — empty stubs do not inflate the score. `harness-loop.sh` gained a `folder_interfaces`
  autofix case that scaffolds slots; a human fills them before the score rises.
- Slimmed `SKILL.md` 622 → 507 lines: moved Codex Multi-Worker operational drivers (Mode A/B
  snippets, output gates, empirical run, tree) into `references/codex-multi-worker-doctrine.md`,
  left a pointer. Eliminates per-load context bloat + cross-file duplication.

### Fixed
- Count drift in `SKILL.md`: "13 hook scripts" → 24; "7 events, 6 patterns" → "8 hooks / 6 events";
  `score-harness.sh` "% of 7 expected events" → 6. Added `stop-e2e.sh`, `folder-claudemd.sh`,
  and `templates/wiki-master-index.template.md` to the shipped-assets table.
- `folder-claudemd.sh` substantive-coverage false-negative: switched from a loose `{[a-z]`
  pattern to exact placeholder-token matching, so a filled folder CLAUDE.md that legitimately
  contains `${var}` / `{type}` is no longer mis-flagged as an empty stub. Placeholder strings
  are now a single source of truth shared by `scaffold()` and `is_substantive()` (no drift).
- `verify-harness.sh`: added a [C2] functional test proving the anti-gaming logic end-to-end
  (no interface → stub → filled = `0 1|0 1|1 1`), with `CLAUDE_PROJECT_DIR` pinned to a sandbox.
  Added [C3] proving `stop-e2e.sh` no-ops safely (stop_hook_active / no package.json → exit 0).
- **`drift-scan.sh` toothless-gate bug**: checks [1/6] pointers, [2/6] hook scripts, [3/6] MCP
  ran `warn` inside `... | while` pipelines, so `fail_count++` happened in a subshell and was lost
  — drift-scan printed "✗ broken pointer" yet still reported PASS / exit 0. Converted all three to
  process substitution so the gate actually fails. [1/6] now also validates **folder-level**
  CLAUDE.md pointers, resolved relative to each file's own directory.
- `bootstrap.sh` folder-scaffold step gated on the *project copy* of `folder-claudemd.sh`, which
  does not exist under `DRY_RUN` (never copied) — so a dry run silently skipped reporting folder
  CLAUDE.md intent. Now calls the source script (`$SKILL_DIR/folder-claudemd.sh`) with
  `CLAUDE_PROJECT_DIR` set, so dry-run preview is accurate. (Caught by a read-only run against a
  real repo; the synthetic tests had pre-copied the script and masked it.)

## 2.0.0 — 2026-05-13

### Added
- **3 subagents** (`agents/`): `harness-planner`, `harness-generator`, `harness-evaluator` — Anthropic March 2026 multi-agent pattern with file-based handoff via `.claude/harness/spec.md` and sprint contracts.
- **8 slash commands** (`commands/`): `/harness-setup`, `/harness-loop`, `/harness-score`, `/harness-verify`, `/harness-drift`, `/harness-plan`, `/harness-build`, `/harness-qa`.
- **Canonical Anthropic harness hooks** (`scripts/`): `track-read.sh`, `verify-gate.sh` (Default-FAIL gate), `kill-switch.sh`, `steer.sh`, `commit-on-stop.sh` — from `anthropics/cwc-long-running-agents`.
- **Telemetry pipeline**: `telemetry.sh` (PostToolUse jsonl + OTLP), `weekly-metrics.sh` (jq-based reports), `templates/grafana-dashboard.json` (6-panel ready-to-import).
- **Cost guardrails**: `budget-guard.sh` (PreToolUse daily/harness cap), `poll-cost.sh` (Anthropic Admin API daily cost poll, cron-friendly).
- **Plan Mode + Extended Thinking integration**: `references/plan-mode-and-thinking.md` + `session-start.sh` adaptive verbosity based on `effort.level` stdin field.
- **Codex parity**: `templates/AGENTS.md.template` (AAIF standard) + `templates/codex-hooks.json.template` (Bash-only Codex hooks). Bootstrap auto-detects `.codex/` and scaffolds both.
- **Plugin manifest**: `.claude-plugin/plugin.json` for marketplace distribution.

### Changed
- `scripts/bootstrap.sh` now copies subagents + slash commands into `.claude/agents/` and `.claude/commands/`.
- `session-start.sh` adapts verbosity to `effort.level` (low → minimal, otherwise → full git log + PROGRESS).
- Bootstrap script list expanded from 10 → 22 scripts.

### Confirmed (from latest research)
- Subagents cannot spawn other subagents — use Skills with `context: fork` for nesting.
- Subagent frontmatter supports `memory: project`, `effort: medium`, `isolation: worktree`, `skills: [...]` for preloading skill bodies.
- New PreToolUse return field `updatedInput` lets hooks REWRITE tool calls (not just allow/deny).
- MCP tools support `defer_loading: true` — enables 100-server catalogs without context bloat.
- 28+ hook events in 2026 (vs 8 in 2025). Anthropic added `SubagentStart`, `TaskCreated/Completed`, `TeammateIdle`, `Setup`, `PostToolUseFailure`, `WorktreeCreate/Remove`, etc.

## 1.0.0 — 2026-05-13

Initial release. 14-dimension scorer, autonomous score → loop → verify orchestrator, 6-layer security model, drift-scan, multi-language support (Python/Node/Go/Rust/Swift/Kotlin/Ruby/.NET/Elixir/PHP/Java).
