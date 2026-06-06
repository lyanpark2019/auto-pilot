---
description: >
  Harness operations router — setup (idempotent bootstrap/audit, --dry-run),
  drift (6-check scanner), loop (autonomous score→fix→re-score, target/max args),
  score (14-dim score → .claude/score.json), verify (7 functional hook tests A-G).
  Replaces /harness-setup /harness-drift /harness-loop /harness-score /harness-verify.
argument-hint: "<setup|drift|loop|score|verify> [setup: --dry-run | loop: target max]"
allowed-tools: Bash(bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/*.sh), Bash(bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/*.sh), Read, Glob
---

# /harness-ops

Single-command router for all harness operations. Subcommand consumes `$1`; loop's target/max are `$2`/`$3`.

```
/harness-ops setup [--dry-run]     # idempotent bootstrap; --dry-run prints the command only
/harness-ops drift                 # 6-check drift scan; falls back to bundled scanner
/harness-ops loop [target] [max]   # autonomous score→fix→re-score (default: 95 15)
/harness-ops score                 # 14-dim score → .claude/score.json
/harness-ops verify                # 7 functional hook tests A-G
```

!`case "$1" in
  setup)  if [ "$2" = "--dry-run" ]; then echo "DRY_RUN=1 bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh"; else bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh; fi ;;
  drift)  if [ -x "${CLAUDE_PROJECT_DIR}/.claude/scripts/drift-scan.sh" ]; then bash "${CLAUDE_PROJECT_DIR}/.claude/scripts/drift-scan.sh"; else echo "(no project-local .claude/scripts/drift-scan.sh — using bundled scanner; run /harness-ops setup to install the project hook)"; bash "${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/drift-scan.sh"; fi ;;
  loop)   TARGET="${2:-95}" MAX_ITERATIONS="${3:-15}" bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/harness-loop.sh ;;
  score)  bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/score-harness.sh | jq . ;;
  verify) bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/verify-harness.sh ;;
  *)      echo "usage: /harness-ops <setup|drift|loop|score|verify>" ;;
esac`

---

## setup mode

Bootstrap or audit the Claude Code harness in this project. Idempotent — re-running merges with existing config.

- `--dry-run` → prints the bootstrap command without executing it (no side effects).

If this project already has `CLAUDE.md`, the bootstrap runs in **merge mode** — adds missing pieces, never overwrites.

The bootstrap detects stack (Python/Node/Go/Rust/Swift/Kotlin/Ruby/.NET), copies 13 hook scripts to `.claude/scripts/`, merges hook registrations via `(event, matcher, command)` tuple dedupe into `.claude/settings.local.json`, scaffolds `CLAUDE.md` (≤50 lines, pointer-style) if absent, creates `docs/adr/0001-record-architecture-decisions.md`, and updates `.gitignore`.

After bootstrap completes, run `/harness-ops drift` to verify.

---

## drift mode

Run the drift scanner — 6 checks for stale pointers, missing hook scripts, MCP↔deps mismatch, forbidden patterns in code, ADR coverage, security baseline.

Project-local scanner (`.claude/scripts/drift-scan.sh`) is preferred; bundled fallback used if absent (with install hint).

6-check report:

1. CLAUDE.md pointer targets — every `[link](path)` resolves
2. Hook scripts — each entry in settings.local.json points to an executable file
3. MCP ↔ dependency consistency — registered MCP servers correspond to declared deps
4. Forbidden patterns — `git add -A/.` in shell scripts, oversize `any` usage in TS, files >300 lines
5. ADR coverage — count + presence
6. Security baseline — PreToolUse(Bash) guard, UserPromptSubmit secret scan, `.env` in gitignore

Exit 0 = PASS. Exit 1 = FAIL with itemized issues.

---

## loop mode

Autonomous score → loop → verify orchestrator. Iteratively fixes the lowest-scoring dimension until target reached.

```
/harness-ops loop             # default: target=95, max=15
/harness-ops loop 100 20      # override (old: /harness-loop 100 20)
```

Exit codes:
- `0` — target reached, verify-harness ran and reported pass/fail
- `1` — max iterations without target
- `2` — stuck (all dimensions attempted, no score progress) — outputs lowest 5 dimensions

The loop scores 14 dimensions (philosophy, claudemd, hooks_coverage, hooks_json_format, security, drift_detection, linter, adr, automation, idempotency, evals, gitignore, mcp_hygiene, sandbox), identifies the lowest, applies the matching autofix, and re-scores. Reads `.claude/score.json` between iterations.

---

## score mode

Score this project's harness across 14 dimensions. Writes `.claude/score.json` and prints a summary via `jq .`.

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

---

## verify mode

Final verification — runs 7 functional hook tests independent of the scorer. Catches "scored high but hook doesn't trigger" cases.

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
