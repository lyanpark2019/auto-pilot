---
name: harness-loop
description: Autonomous score → loop → verify orchestrator. Iteratively fixes the lowest-scoring dimension until target reached. Default target 95, max 15 iterations.
argument-hint: "[target=95] [max=15]"
allowed-tools: Bash(bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/*.sh), Read, Glob
---

Run the autonomous harness improvement loop.

Defaults: `TARGET=95 MAX_ITERATIONS=15`. Override via arguments: `/harness-loop 100 20`.

!`TARGET="${1:-95}" MAX_ITERATIONS="${2:-15}" bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/harness-loop.sh`

Exit codes:
- `0` — target reached, verify-harness ran and reported pass/fail
- `1` — max iterations without target
- `2` — stuck (all dimensions attempted, no score progress) — outputs lowest 5 dimensions

The loop scores 14 dimensions (philosophy, claudemd, hooks_coverage, hooks_json_format, security, drift_detection, linter, adr, automation, idempotency, evals, gitignore, mcp_hygiene, sandbox), identifies the lowest, applies the matching autofix, and re-scores. Reads `.claude/score.json` between iterations.
