---
name: harness-score
description: Score this project's harness across 14 dimensions. Writes .claude/score.json and prints a summary.
allowed-tools: Bash(bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/score-harness.sh), Read
---

!`bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/score-harness.sh | jq .`

Dimensions:

- `philosophy` — CLAUDE.md exists with reason column
- `claudemd` — line count vs IFScale thresholds (≤50 → 100, ≤80 → 85, ≤150 → 60, >150 → 30)
- `hooks_coverage` — % of 7 expected hook events registered
- `hooks_json_format` — PostToolUse uses `hookSpecificOutput.additionalContext`
- `security` — 6-layer count (deny rules, PreToolUse, sandbox, scan-secrets, injection-defender, CLAUDE.md prose)
- `drift_detection` — drift-scan.sh exists + passes
- `linter` — Rust-based fast linter present (Oxlint/Biome/Ruff/gofumpt/clippy)
- `adr` — number of ADRs in docs/adr/ (3+ → 100)
- `automation` — bootstrap, drift-scan, session-start, PROGRESS.json present
- `idempotency` — settings.local.json has no duplicate (matcher, command) tuples
- `evals` — eval scenarios defined
- `gitignore` — .env*, .claude runtime files ignored
- `mcp_hygiene` — no Playwright MCP for self-test (use Playwright CLI instead)
- `sandbox` — .claude/sandbox.sb present
