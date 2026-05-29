---
name: harness-verify
description: Final verification agent — runs 7 functional hook tests independent of the scorer. Catches "scored high but hook doesn't trigger" cases.
allowed-tools: Bash(bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/verify-harness.sh), Read
---

!`bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/verify-harness.sh`

Checks:

- **[A] Script integrity** — syntax + executable bit
- **[B] Hook registration** — settings.local.json has all 7 events; no duplicate (matcher, command) tuples
- **[C] Functional hook tests** — actual stdin → exit code verification:
  - guard-bash blocks `git commit --no-verify`
  - guard-bash allows benign `ls`
  - block-env-edit blocks `.env`
  - block-env-edit allows `src/main.py`
  - protect-lint-config blocks `pyproject.toml`
  - scan-secrets blocks AWS key pattern
  - scan-secrets allows benign text
- **[D] PostToolUse JSON format** — `hookSpecificOutput.additionalContext` present
- **[E] CLAUDE.md compliance** — line count vs thresholds, prohibitions have "why" column
- **[F] Drift scan** — full drift-scan.sh run
- **[G] Score reconciliation** — current `.claude/score.json` summary

Exit 0 = verified. Exit 1 = failures (specific items listed).
