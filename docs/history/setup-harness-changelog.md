# setup-harness — distilled changelog

Distilled from `skills/setup-harness/CHANGELOG.md` (deleted) and `README.md` (deleted) on 2026-06-06.
Source was absorbed-plugin residue; non-duplicate durable facts preserved below. SKILL.md is the
live reference; this file is historical provenance only.

## 2.1.0 — 2026-05-25

**Added**
- `scripts/folder-claudemd.sh`: detects dense/layer candidate folders (≥`FOLDER_THRESHOLD`=10 source files) and scaffolds ≤10-line local interfaces. Wired into `bootstrap.sh` + `harness-loop.sh` (claudemd autofix).
- `scripts/stop-e2e.sh`: Playwright CLI smoke Stop hook. `bootstrap.sh` auto-registers it when Playwright dep detected in `package.json`; non-browser projects skip it.

**Changed**
- Scorer dimension count: 14 → **15** (`folder_interfaces` split out from `claudemd`). `claudemd` now measures root file alone; `folder_interfaces` covers substantive folder-level coverage (empty stubs do not count).
- `harness-loop.sh` gained `folder_interfaces` autofix case.
- SKILL.md trimmed 622 → 507 lines: Codex Multi-Worker operational drivers moved to `references/codex-multi-worker-doctrine.md`.

**Fixed**
- `drift-scan.sh` toothless-gate: `fail_count++` was in a subshell (inside `| while`) and lost; converted to process substitution so failures propagate correctly.
- `folder-claudemd.sh` substantive-coverage false-negative: switched from loose `{[a-z]` pattern to exact placeholder-token matching.
- `verify-harness.sh`: added [C2] anti-gaming test + [C3] `stop-e2e.sh` no-op test.
- `bootstrap.sh` dry-run folder-scaffold: was calling project copy (doesn't exist under DRY_RUN); now calls source script directly.
- Count drift in SKILL.md: corrected script counts, hook counts, event counts.

## 2.0.0 — 2026-05-13

**Added (not in SKILL.md)**
- 3 subagents: `harness-planner`, `harness-generator`, `harness-evaluator` (Anthropic Mar 2026 multi-agent pattern, file-based handoff via `.claude/harness/spec.md`).
- 8 slash commands: `/harness-{setup,loop,score,verify,drift,plan,build,qa}`.
- Canonical Anthropic harness hooks from `anthropics/cwc-long-running-agents`: `track-read.sh`, `verify-gate.sh` (Default-FAIL gate), `kill-switch.sh`, `steer.sh`, `commit-on-stop.sh`.
- Telemetry pipeline: `telemetry.sh` (PostToolUse jsonl + OTLP) + `weekly-metrics.sh` + `templates/grafana-dashboard.json`.
- Cost guardrails: `budget-guard.sh` (daily/harness cap) + `poll-cost.sh` (Anthropic Admin API, cron-friendly).
- Plan Mode + Extended Thinking: `references/plan-mode-and-thinking.md` + `session-start.sh` adaptive verbosity (`effort.level`).
- Codex parity: `templates/AGENTS.md.template` (AAIF standard) + `templates/codex-hooks.json.template`. Bootstrap auto-detects `.codex/`.
- Plugin manifest: `.claude-plugin/plugin.json`.

**Research findings confirmed at release**
- Subagents cannot spawn other subagents — use Skills with `context: fork` for nesting.
- New `updatedInput` hook return field lets PreToolUse hooks REWRITE tool calls (not just block).
- MCP `defer_loading: true` enables 100-server catalogs without context bloat.
- 28+ hook events in 2026 (vs 8 in 2025): added SubagentStart, TaskCreated/Completed, TeammateIdle, Setup, PostToolUseFailure, WorktreeCreate/Remove, etc.

## 1.0.0 — 2026-05-13

Initial release. 14-dimension scorer, autonomous score→loop→verify orchestrator, 6-layer security model, drift-scan, multi-language support (Python/Node/Go/Rust/Swift/Kotlin/Ruby/.NET/Elixir/PHP/Java).
