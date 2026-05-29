---
name: harness-drift
description: Run the drift scanner — 6 checks for stale pointers, missing hook scripts, MCP↔deps mismatch, forbidden patterns in code, ADR coverage, security baseline.
allowed-tools: Bash(bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/drift-scan.sh), Bash(bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/drift-scan.sh)
---

!`if [ -x "${CLAUDE_PROJECT_DIR}/.claude/scripts/drift-scan.sh" ]; then bash "${CLAUDE_PROJECT_DIR}/.claude/scripts/drift-scan.sh"; else echo "(no project-local .claude/scripts/drift-scan.sh — using bundled scanner; run /harness-setup to install the project hook)"; bash "${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/drift-scan.sh"; fi`

This is the **executable** version of SKILL.md Step 4. Run it any time — pre-commit, weekly, before a release. Outputs a 6-check report:

1. CLAUDE.md pointer targets — every `[link](path)` resolves
2. Hook scripts — each entry in settings.local.json points to an executable file
3. MCP ↔ dependency consistency — registered MCP servers correspond to declared deps
4. Forbidden patterns — `git add -A/.` in shell scripts, oversize `any` usage in TS, files >300 lines
5. ADR coverage — count + presence
6. Security baseline — PreToolUse(Bash) guard, UserPromptSubmit secret scan, `.env` in gitignore

Exit 0 = PASS. Exit 1 = FAIL with itemized issues.
