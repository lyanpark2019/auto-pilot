---
name: harness-setup
description: Bootstrap or audit the Claude Code harness in this project. Idempotent — re-running merges with existing config.
argument-hint: "[--dry-run]"
allowed-tools: Bash(bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/*.sh), Read, Glob
---

Run setup-harness bootstrap in this project.

!`if [ "$ARGUMENTS" = "--dry-run" ]; then echo "DRY_RUN=1 bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh"; else echo "bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh"; fi`

After bootstrap completes, run `/harness-drift` to verify.

If this project already has `CLAUDE.md`, the bootstrap will run in **merge mode** — adds missing pieces, never overwrites.

The bootstrap detects stack (Python/Node/Go/Rust/Swift/Kotlin/Ruby/.NET), copies 13 hook scripts to `.claude/scripts/`, merges hook registrations via `(event, matcher, command)` tuple dedupe into `.claude/settings.local.json`, scaffolds `CLAUDE.md` (≤50 lines, pointer-style) if absent, creates `docs/adr/0001-record-architecture-decisions.md`, and updates `.gitignore`.
