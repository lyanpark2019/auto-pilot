# setup-harness skill

Bootstrap or audit a complete Claude Code harness for any project.

Doctrine + when-to-use-which (vs `harness-project-docs`): `@~/.claude/docs/harness-engineering.md`.

## Quick start

```bash
# In your project root

# Manual setup (idempotent)
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh

# Audit only — no writes
DRY_RUN=1 bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh

# Drift scan
bash .claude/scripts/drift-scan.sh

# Autonomous: score → loop → verify (recommended)
TARGET=95 MAX_ITERATIONS=15 bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/harness-loop.sh
```

Three-stage orchestrator: `score-harness.sh` → `harness-loop.sh` → `verify-harness.sh`. Loop picks the lowest of 15 dimensions, runs the matching autofix, re-scores, and stops at target or when stuck. Final verification agent runs 7 functional hook tests independent of the scorer (catches "scored high but hook doesn't actually trigger" cases).

## What it ships

```
setup-harness/
├── README.md                          ← you are here
├── SKILL.md                           ← 8-step manual guide + Codex multi-worker mode
├── CHANGELOG.md                       ← v1 → v2.0.0 history
├── .claude-plugin/plugin.json         ← marketplace manifest
├── agents/                            ← 3 subagents (Planner / Generator / Evaluator)
├── commands/                          ← 2 routed commands (/harness, /harness-ops)
├── scripts/                           ← 28 executable: hooks + installer + orchestrator
│   ├── bootstrap.sh                   ← one-shot installer (idempotent, DRY_RUN)
│   ├── score-harness.sh               ← 15-dimension scorer → .claude/score.json
│   ├── harness-loop.sh                ← autonomous loop until target / verify
│   ├── verify-harness.sh              ← final verification agent (7 functional tests)
│   ├── guard-bash.sh                  ← PreToolUse(Bash) — destructive/bypass guard
│   ├── block-env-edit.sh              ← PreToolUse(Edit) — secret file guard
│   ├── protect-lint-config.sh         ← PreToolUse(Edit) — config tamper guard
│   ├── post-edit-lint.sh              ← PostToolUse — fast linter + JSON feedback
│   ├── stop-quality-gate.sh           ← Stop — lint+type+test gate
│   ├── scan-secrets.sh                ← UserPromptSubmit — credential scan
│   ├── injection-defender.sh          ← PostToolUse(Read/Web/Bash) — injection warn
│   ├── session-start.sh               ← SessionStart — git log + PROGRESS injection
│   ├── pre-compact-save.sh            ← PreCompact — state persistence
│   ├── drift-scan.sh                  ← Step 4 executable
│   ├── codex-analyze.sh               ← Opus-PM + Codex-worker dispatch
│   ├── track-read.sh / verify-gate.sh / kill-switch.sh / steer.sh / commit-on-stop.sh
│   │                                  ← canonical Anthropic cwc-long-running-agents hooks
│   ├── telemetry.sh / weekly-metrics.sh
│   │                                  ← PostToolUse jsonl + OTLP, jq weekly report
│   └── budget-guard.sh / poll-cost.sh ← daily/harness spend cap + cost poll
├── templates/                         ← copy-and-edit
│   ├── CLAUDE.md.template             ← pointer-style ≤50-line scaffold
│   ├── AGENTS.md.template             ← AAIF standard (Codex / Cursor / Devin)
│   ├── codex-hooks.json.template      ← Bash-only Codex hooks
│   ├── ADR-template.md                ← immutable ADR + enforcement
│   ├── lefthook.yml.template          ← multi-stack pre-commit
│   ├── sandbox.sb.template            ← macOS Seatbelt profile
│   ├── grafana-dashboard.json         ← 6-panel dashboard for telemetry pipeline
│   └── wiki-harness-engineering/      ← index/principle/layer skeletons for Codex doctrine vault
├── references/                        ← deep dives
│   ├── hook-templates.md              ← JSON additionalContext patterns
│   ├── mcp-catalog.md                 ← MCP tax + CLI-first
│   ├── prohibition-patterns.md        ← AI anti-patterns + OpenAI 4 cat
│   ├── language-stacks.md             ← 10 languages
│   ├── sandbox-and-security.md        ← 6-layer threat model
│   ├── measuring-harness.md           ← metrics + strip-when guide
│   ├── plan-mode-and-thinking.md      ← Plan Mode + Extended Thinking workflow
│   └── codex-multi-worker-doctrine.md ← 15 principles + 12 sources (Opus PM + Codex workers)
└── evals/
    └── evals.json                     ← 6 eval scenarios
```

## When to use this skill

- Joining a new project — bootstrap from zero
- Auditing existing project — find March 2026 best-practice gaps
- Setting up multi-agent (Planner/Generator/Evaluator) harness for long autonomous tasks
- Hardening a public-facing service — install 6-layer security
- Migrating from ESLint/Flake8 to Rust-based fast linters (Oxlint/Biome/Ruff)

## When NOT to use this skill

- Adding a single MCP server → use the MCP server's own setup
- Writing one slash command → use `Skill` tool guide
- Writing one hook → write directly in `.claude/settings.local.json`
- Documenting an existing harness → use the Codex `harness-project-docs` skill (see doctrine)

## Skill activation

Marked `disable-model-invocation: true` — model does NOT auto-invoke. Trigger via:

```
/setup-harness
```

Or explicit invocation in conversation. Intentional: harness setup is a structural decision; auto-triggering on every keyword would be noisy.

## Core principles + Primary sources

See doctrine: `@~/.claude/docs/harness-engineering.md` — "Shared rules", "Anti-patterns", and "Primary sources" are canonical there.

## License

User's private skill. No external license.
