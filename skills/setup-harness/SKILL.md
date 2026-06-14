---
name: setup-harness
description: "Bootstrap or audit a complete Claude Code harness for any project — CLAUDE.md (root + folder-level), hooks, .mcp.json, subagents, commands, sandbox, and code↔doc drift detection. Includes autonomous score+loop+verify orchestrator. Implements harness-engineering best practices. Use this skill whenever the user wants to set up, bootstrap, configure, or audit the full Claude Code harness for a project. Trigger phrases: 'harness setup', 'set up harness', 'configure Claude Code for this project', 'create CLAUDE.md', 'bootstrap harness', 'harness engineering', '하네스 세팅', '하네스 점검', 'Claude Code 세팅', 'CLAUDE.md 만들어줘', 'hook 세팅', 'drift check', 'score harness', 'harness loop', '하네스 점수', joining a new project and wanting project-level rules, hooks, and automations. This skill handles the FULL harness (multiple components together) — for adding a single MCP server, creating one slash command, or writing one hook, use the relevant specific skill instead."
---

# Setup Harness

Bootstrap a complete Claude Code harness in 8 steps. Works on any project.

## TL;DR

```bash
# Manual: install (idempotent)
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh

# Audit only (no writes)
DRY_RUN=1 bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh

# Drift scan (executable Step 4)
bash .claude/scripts/drift-scan.sh

# Autonomous: score → loop → verify (recommended)
TARGET=95 MAX_ITERATIONS=15 bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/harness-loop.sh
```

Detects stack → copies 24 hook/automation scripts → merges 9 base hook entries (6 events) via `(event,matcher,command)` tuple dedupe → scaffolds root CLAUDE.md (≤50 lines) + folder-level CLAUDE.md (dense/layer folders) + ADR + .gitignore + PROGRESS.json. Browser projects get one optional extra Stop hook. Re-running never doubles. See `README.md` for the file tree.

## Autonomous score+loop+verify orchestrator

Three coordinated scripts implement the closed loop:

| Script | Role |
|--------|------|
| `score-harness.sh` | 15-dimension scorer → `.claude/score.json` |
| `harness-loop.sh` | score → pick lowest dim → autofix → re-score; resets attempted-list on improvement; bails after stuck detection. Scopes the **harness config** (CLAUDE.md / hooks / drift / mcp — the 15 dims below), NOT application code quality. For code-quality scoring + improvement, the loop step delegates to `adversarial-review-loop` codebase mode (13-dim `quality-eval` rubric) — this loop does not re-implement a competing code-quality engine. |
| `verify-harness.sh` | independent final agent — script integrity, hook registration, **7 functional hook tests** (guard-bash blocks --no-verify, block-env-edit blocks .env, scan-secrets blocks AWS keys, etc.), JSON-format check, CLAUDE.md compliance, drift, score reconciliation |

The 15 dimensions scored: philosophy, claudemd (root only), folder_interfaces, hooks_coverage, hooks_json_format, security, drift_detection, linter, adr, automation, idempotency, evals, gitignore, mcp_hygiene, sandbox. `claudemd` measures the root file alone; `folder_interfaces` separately scores substantive folder-level CLAUDE.md coverage (no candidate folders → 100, so it never penalizes small projects; raise `FOLDER_THRESHOLD` to opt out).

Exit codes from `harness-loop.sh`:
- `0` — target reached, verify-harness ran and reported pass/fail
- `1` — max iterations without target
- `2` — stuck (all dims attempted, no score progress) — outputs lowest 5 dims for human

## Philosophy

See `@~/.claude/docs/harness-engineering.md` (sections "Shared rules" + "Anti-patterns") for the doctrine. Morph: harness shifts SWE-bench +22pt vs model +1pt — the harness, not the model, is the lever.

## Execution Flow

```
1. Scan → 2. CLAUDE.md (pointer-style) → 3. Hooks (9 base hook entries / 6 events, plus optional browser Stop hook) → 4. Drift Detection
→ 5. MCP → 6. Agents/Commands → 7. Sandbox + Security → 8. Verify
```

Run each step in order. Present results after each step and wait for user confirmation before proceeding. **Idempotent**: re-running on existing setup adds only what is missing (tuple-dedupe by `(event, matcher, command)`).

### Fast path (automated)

This skill ships a `bootstrap.sh` that performs the full 8-step setup non-destructively:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh
```

This auto-detects stack, copies hook scripts to `.claude/scripts/`, merges hooks into `.claude/settings.local.json` (tuple-dedupe), scaffolds `CLAUDE.md`, creates `docs/adr/`, and stamps `.gitignore`. Use this for greenfield. For audit-only on existing harness, skip bootstrap and run the 8 steps interactively.

After bootstrap, generate an environment-constraints block for the repo (shell, BSD/GNU userland, tool versions, CI runners). `--into` upserts a marker-delimited block — re-runs replace it instead of duplicating the header:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/generate_env_constraints.sh [REPO_PATH] --into CLAUDE.md
```

Build-only (W2); apply runs are W3. PickL-API excluded → W4-1.

### Shipped assets

Ready to copy or invoke from this skill directory:

| Path | Purpose |
|------|---------|
| `scripts/bootstrap.sh` | One-shot installer, idempotent |
| `scripts/generate_env_constraints.sh` | Emit `## Environment Constraints` block (marker-wrapped; `--into FILE` = idempotent upsert): shell, BSD/GNU userland, pinned tool versions, CI runner topology |
| `scripts/guard-bash.sh` | PreToolUse(Bash) — block destructive, --no-verify, force-push, git add -A, curl\|bash, sudo |
| `scripts/block-env-edit.sh` | PreToolUse(Write/Edit) — block .env, SSH, AWS, PEM |
| `scripts/protect-lint-config.sh` | PreToolUse(Write/Edit) — block linter/type config edits (prevents agent silencing) |
| `scripts/post-edit-lint.sh` | PostToolUse — per-language fast linter + JSON `additionalContext` feedback |
| `scripts/stop-quality-gate.sh` | Stop — lint+type+test gate, throttled |
| `scripts/stop-e2e.sh` | Stop — Playwright CLI smoke gate, auto-registered when bootstrap detects a Playwright dep, throttled |
| `scripts/scan-secrets.sh` | UserPromptSubmit — AWS/GH/Anthropic/OpenAI/Stripe/Slack/PEM/BIP39 patterns |
| `scripts/injection-defender.sh` | PostToolUse(Read/WebFetch/Bash) — warn on prompt-injection patterns |
| `scripts/session-start.sh` | SessionStart — inject branch + git log + PROGRESS.json |
| `scripts/pre-compact-save.sh` | PreCompact — persist load-bearing state before compaction |
| `scripts/drift-scan.sh` | Executable Step 4 drift report |
| `scripts/score-harness.sh` / `harness-loop.sh` / `verify-harness.sh` | 15-dim score + autonomous loop + final 7-test verifier |
| `scripts/folder-claudemd.sh` | Detect dense/layer folders + scaffold ≤10-line folder CLAUDE.md (`candidates` / `coverage` / `scaffold`) |
| `scripts/codex-analyze.sh` | Opus-PM + Codex-worker dispatch (`init` / `dispatch` / `spawn` / `verify` / `publish`) |
| `scripts/track-read.sh` / `verify-gate.sh` / `kill-switch.sh` / `steer.sh` / `commit-on-stop.sh` | Reimplemented from `anthropics/cwc-long-running-agents` hook patterns (Apache-2.0); no upstream text retained |
| `scripts/telemetry.sh` / `weekly-metrics.sh` | PostToolUse jsonl + OTLP emitter, jq weekly report |
| `scripts/budget-guard.sh` / `poll-cost.sh` | PreToolUse daily/harness spend cap + Anthropic Admin API cost poll |
| ~~`agents/harness-planner.md` / `harness-generator.md` / `harness-evaluator.md`~~ | Deleted 2026-06-07 — 1:1 duplicate of auto-pilot loop; use `/auto-pilot` instead |
| ~~`commands/harness.md` / `commands/harness-ops.md`~~ | Deleted 2026-06-07; use scripts directly: `bootstrap.sh` (setup), `harness-loop.sh` (loop), `score-harness.sh` (score), `verify-harness.sh` (verify), `drift-scan.sh` (drift), `/auto-pilot` (plan/build) |
| `templates/CLAUDE.md.template` | Pointer-style ≤50-line scaffold |
| `templates/AGENTS.md.template` | AAIF standard for Codex/Cursor/Devin parity |
| `templates/ADR-template.md` | Immutable ADR with enforcement section (archgate pattern) |
| `templates/lefthook.yml.template` | Pre-commit complement, multi-stack |
| `templates/codex-hooks.json.template` | Codex (Bash-only) hooks; bootstrap auto-detects `.codex/` |
| `templates/sandbox.sb.template` | macOS Seatbelt profile for `/sandbox` |
| `templates/grafana-dashboard.json` | 6-panel Grafana dashboard for the telemetry jsonl+OTLP pipeline |
| `templates/wiki-harness-engineering/` | Index/principle/layer skeletons for the Codex-worker doctrine vault tree |
| `templates/wiki-master-index.template.md` | Top-level vault index skeleton for multi-project harness docs |
| `evals/evals.json` / `.claude-plugin/plugin.json` | 6 eval scenarios + marketplace manifest |

## Step 1: Scan

> Resolve project context before scanning: `skills/auto-pilot/references/project-context-resolution.md`.

Detect project profile automatically:

```bash
# Project type
ls package.json pyproject.toml Cargo.toml go.mod pom.xml build.gradle Gemfile composer.json 2>/dev/null

# Framework detection (Python)
grep -l "fastapi\|django\|flask" requirements.txt pyproject.toml 2>/dev/null
# Framework detection (Node)
grep -lE "\"(next|express|vue|react|svelte|nuxt|astro)\"" package.json 2>/dev/null
# Framework detection (others)
ls Package.swift 2>/dev/null  # Swift
ls *.csproj 2>/dev/null       # .NET

# DB / infra
grep -lE "supabase|prisma|mongoose|sqlalchemy|pg|psycopg" requirements.txt package.json pyproject.toml 2>/dev/null

# CI/CD
ls .github/workflows/*.yml .gitlab-ci.yml Jenkinsfile 2>/dev/null

# Existing harness (avoid conflicts — switch to merge mode)
find . -name "CLAUDE.md" -o -name "AGENTS.md" 2>/dev/null | grep -v node_modules
ls .claude/ .mcp.json .codex/ 2>/dev/null

# Incident history (prohibition sources)
git log --oneline --grep="fix\|revert\|hotfix\|bug\|incident\|rollback" | head -30

# Large files (modularization candidates)
find . \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.go' -o -name '*.rs' -o -name '*.swift' -o -name '*.kt' \) -not -path '*/node_modules/*' -not -path '*/.venv/*' | xargs wc -l 2>/dev/null | sort -rn | head -10

# Folder structure
find . -type d -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/__pycache__/*' -not -path '*/.venv/*' -not -path '*/dist/*' -not -path '*/build/*' -maxdepth 3 | sort

# Existing ADRs (don't duplicate)
ls docs/adr docs/decisions adr 2>/dev/null
```

**Output**: project profile summary table. If existing CLAUDE.md found → switch to **merge mode** (additive, never overwrite). If `.codex/` found → note dual-platform setup; share AGENTS.md surface.

## Step 2: CLAUDE.md (pointer-style, ≤50 lines root)

CLAUDE.md is a **pointer**, not documentation. It tells the agent where to look (commands, ADRs, linter rules) and what *not* to do (with reasons). Descriptions of "how the system works" go in tests and ADRs — those don't rot.

### Root template (≤50 lines target)

In **merge mode** existing length may exceed 50; preserve content and add only what is missing. The 50-line target applies to fresh creation.

```markdown
# CLAUDE.md

{one-line project description}

## Commands
` ` `bash
{build/test/lint — 3 lines max}
` ` `

## Routing
- ADRs: `docs/adr/`
- Linter rules: `{eslint.config.js | pyproject.toml | .golangci.yml | Cargo.toml}`
- Skills: `.claude/skills/`
- Folder-specific rules: see table below

## 절대 금지 (Prohibitions)
| 금지 | 이유 (ADR/사고/PR 링크) |
|------|------------------------|
| `git commit --no-verify` | bypasses pre-commit linter — ADR-001 |
| `--dangerously-skip-permissions` | disables safety hooks |
| {prohibition} | {actual incident / PR / ADR} |

## 폴더별 상세
| 폴더 | 내용 |
|------|------|
| [{path}/CLAUDE.md]({path}/CLAUDE.md) | one line |
```

**What NOT to write** (these all rot and burn context):
- Tech stack explanation (agent reads `package.json` / `pyproject.toml`)
- Architecture overview prose (encode as type definitions + structural tests instead)
- Verbose style guides (delegate to linter)
- "How this system currently works" (test suite is source of truth)

**Compression**: Vercel cut 40KB → 8KB with 100% pass rate. For every line ask "would deleting this cause the agent to err?" If no → delete.

### Prohibition Mining

Source priority: ① `git log --grep="fix|revert|hotfix|incident"` (real bugs) ② SDK/infra constraints (e.g., RPC `search_path=""`, pooler DDL limits) ③ Implicit rules (timezones, naming) ④ AI anti-patterns (`any` abuse, ghost files, comment floods, 36-40% AI code ships with security issues — `references/prohibition-patterns.md`).

**Every prohibition must have a "why"** — ADR/PR/incident link. Prohibitions without reasons get ignored.

### Folder-Level (≤10 lines each)

Target folders, priority order:

1. **Incident-heavy folders** — git log concentrates fix/revert here
2. **Layer boundaries** — DB / service / API / test with distinct responsibilities
3. **10+ source files** — needs conventions for consistency

```markdown
# {Layer} — 금지 사항

- **{prohibition}** — {reason, link to ADR-NNN}
```

**Automated (scaffold) + human (fill)**: `bootstrap.sh` and `harness-loop.sh` call
`scripts/folder-claudemd.sh`, which detects candidate folders (≥10 source files by default,
`FOLDER_THRESHOLD` tunable) and drops a stub interface in each that lacks one. The `claudemd`
score blends 70% root-budget + 30% folder-coverage — but **a folder counts as covered only
once its `{placeholder}` tokens are replaced with real rules**. An empty stub scores nothing,
so the metric can't be gamed by file creation. The loop scaffolds the slots; you fill them
with evidence-backed prohibitions, then the score rises.

### Proportionality

Fewer than 5 source files? Stick to framework-safe defaults (git safety, secrets, logging). Don't prescribe architecture the project hasn't earned. Note where to expand as it grows.

### AGENTS.md compatibility

If `.codex/` exists or project ships AGENTS.md, add `@AGENTS.md` at top of CLAUDE.md. AGENTS.md (AAIF/Linux Foundation) is read natively by Codex/Cursor/Devin/Copilot. CLAUDE.md stays Claude Code specific (Hooks, Plan Mode).

## Step 3: Hooks (9 base hook entries across 6 events)

Hooks are where the harness actually enforces. Six Claude Code hook events are wired in the base install (PreToolUse 3, PostToolUse 2, Stop/UserPromptSubmit/SessionStart/PreCompact one each → 9 hook entries total; browser projects add an optional Stop entry):

| Event | Pattern | Script | Bypass behavior |
|-------|---------|--------|-----------------|
| **PreToolUse**(Bash) | Safety Gate | `guard-bash.sh` | exit 2 + stderr → fed back to agent |
| **PreToolUse**(Write\|Edit\|MultiEdit) | Secret Gate | `block-env-edit.sh` + `protect-lint-config.sh` | exit 2 |
| **PostToolUse**(Write\|Edit\|MultiEdit) | Quality Loop | `post-edit-lint.sh` | JSON `hookSpecificOutput.additionalContext` → self-correction |
| **PostToolUse**(Read\|WebFetch\|Bash) | Injection Defender | `injection-defender.sh` | additionalContext warning, non-blocking |
| **Stop** | Completion Gate | `stop-quality-gate.sh` | `decision: "block"` + reason — checks `stop_hook_active` to avoid loop |
| **UserPromptSubmit** | Secret Scanner | `scan-secrets.sh` | exit 2 → prompt never reaches model or transcript |
| **SessionStart** | Continuity | `session-start.sh` | additionalContext with git log + PROGRESS.json |
| **PreCompact** | State Persistence | `pre-compact-save.sh` | non-blocking — persist before context drop |

`SubagentStop` is supported by Claude Code but optional; reuse `stop-quality-gate.sh` if needed.

### Critical: feedback injection, not stdout

PostToolUse stdout is **not** treated as agent context. To inject feedback, the hook must emit docs-compliant JSON:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "handler.ts:42, 78, 103 — 3 TypeScript errors:\n..."
  }
}
```

The agent sees `additionalContext` in its next turn and self-corrects. A hook that only blocks (exit 2) stops the process; a hook that injects context drives the fix forward.

### Per-language fast linter

PostToolUse hooks need to finish in **milliseconds** — Rust-based tools (Biome/Oxlint/Ruff) are 50–100x faster than ESLint/Flake8. Full per-language stacks (TS/Py/Go/Rust/Swift/Kotlin/Ruby/.NET/Elixir/PHP/Java + SQL/infra): `references/language-stacks.md`.

### Stack → Hook Mapping

| Detection | Hook | Script |
|-----------|------|--------|
| Python + ruff/pytest | Stop: quality gate | `stop-quality-gate.sh` |
| Node + Biome/Oxlint | PostToolUse(Write\|Edit\|MultiEdit): auto-fix + inject | `post-edit-lint.sh` |
| Any git repo | PreToolUse(Bash): block destructive + `--no-verify` | `guard-bash.sh` |
| .env exists | PreToolUse(Edit): block secret edits | `block-env-edit.sh` |
| Linter config exists | PreToolUse(Edit): **block lint config tampering** | `protect-lint-config.sh` |
| Browser app | Stop: Playwright CLI smoke | `stop-e2e.sh` |

### Config protection (critical, often missed)

When a linter error fires, agents commonly silence it by editing `.eslintrc` / `biome.json` / `pyproject.toml` instead of fixing code. Block that edit at PreToolUse:

```bash
PROTECTED=".eslintrc eslint.config biome.json pyproject.toml .prettierrc tsconfig.json lefthook.yml .golangci.yml Cargo.toml .swiftlint.yml .pre-commit-config.yaml"
# ...emit BLOCKED on stderr + exit 2
```

See `references/hook-templates.md` for full scripts.

### Script Permissions

```bash
chmod +x .claude/scripts/*.sh
```

Required after writing. Hook bash entries silently no-op if non-executable.

### Registration

Use `.claude/settings.local.json` by default (developer-local). For team-wide hooks (e.g., security), use `.claude/settings.json` and commit it. Merge into existing JSON — never overwrite. Dedupe by `(event, matcher, command)` tuple when re-running.

## Step 4: Drift Detection (run now)

Drift detection is not future tooling — execute the grep/scan **right now** and report findings:

| Check | Command | Action on miss |
|-------|---------|---------------|
| Prohibitions vs code | `grep -rn "{forbidden_pattern}" --include="*.{ext}" src/` | List violations |
| CLAUDE.md pointer targets | for each `[link]({path})` → `test -f {path}` | Remove stale pointers |
| `.mcp.json` vs deps | jq + grep dependency list | Flag mismatches |
| Hook script paths | jq settings.json → test -x | Report missing/non-exec scripts |
| Agent code references | grep for agent's named functions/files | Flag stale agents |
| ADR ↔ rule binding | each ADR-NNN.md → grep for corresponding lint rule | Suggest archgate-style coupling |

Pointer-style CLAUDE.md has a built-in advantage: **broken pointers fail loudly** (file 404), unlike descriptive docs which rot silently.

**Output**: drift report table. Auto-fix safe items (remove dead pointers); flag risky items (code violations) for user.

### Step 4b: Install committed pre-push doc-drift hook

The grep/scan above is the one-shot audit. For ongoing protection, install the
committed pre-push gate so future pushes flag stale `file:line` citations
**before** they land in a PR — same trick as deichrenner/driftcheck, but pure
grep+wc (no LLM cost, runs in <1s).

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/install-drift-hook.sh" .
```

That installs `scripts/quality/check_doc_drift.sh` into the repo and appends a
`drift:` entry to `lefthook.yml` (creating it if absent). Then `lefthook install`
activates the git hook.

If the project's docs cite module-relative paths (e.g. `cli/x.py` meaning
`src/myproj/cli/x.py`), export `DRIFT_FALLBACK_PREFIX=src/myproj` so the
detector resolves them — otherwise legitimate convention citations flag as
MISSING. Also wire a `SessionStart` hook in `.claude/settings.json` that runs
the same script and emits the report via `additionalContext` so agents see
drift at session top.

## Step 5: MCP

Detect dependencies → recommend MCP servers → create `.mcp.json`. **Skip what plugins already provide.**

### Dependency → MCP Mapping

| Detection | MCP Server | Notes |
|-----------|-----------|-------|
| supabase in deps | supabase | official MCP |
| sentry-sdk in deps | sentry | official MCP |
| GitHub repo | github | use `gh` CLI alternative if heavy MCP tax matters |
| pg/psycopg/mongoose | postgres / mongodb | varies |
| Browser app | **Playwright CLI** (NOT MCP) | MCP tax ~114K tokens/task; CLI ~27K |
| iOS app | XcodeBuildMCP | Sentry-acquired, 59 tools |
| Android/iOS shared | mobile-mcp | accessibility-tree-based |
| API project | Hurl (CLI, no MCP) | plain-text HTTP tests |
| Popular libs | context7 | check plugin first |

### MCP tax warning

Each MCP server consumes context window via tool definitions. Playwright MCP alone: 26+ tool definitions, 3,000+ accessibility nodes per snapshot. Prefer **CLI tools** for E2E (Playwright CLI 4x cheaper, agent-browser 5.7x cheaper). Reserve MCP for tasks that genuinely need protocol-level features.

See `references/mcp-catalog.md`.

## Step 6: Agents & Commands

Recommend project-specific subagents + slash commands. Present, let user select.

### Pattern → Recommendation

| Detection | Type | Name | Purpose |
|-----------|------|------|---------|
| pytest/jest exists | Command | `/qg` | Quality gate (lint+type+test) |
| .sql migrations | Agent | `rpc-schema-validator` | RPC ↔ table cross-check |
| API routes | Agent | `contract-drift-checker` | Endpoint/header/table drift |
| Long-task project (>2hr) | Pattern | Planner + Generator + Evaluator | GAN-inspired 3-agent harness (Anthropic 2026) |
| Any project | Command | `/setup-harness` | Self-reference for re-running |

### When to use multi-agent

Tasks beyond model solo capability: **planner** (1-line→spec) + **generator** (feature-by-feature) + **evaluator** (Playwright QA, hard threshold, blocks completion). Cost: 20x solo. Justified at model capability boundary; strip when model upgrades make a layer non-load-bearing.

## Step 7: Sandbox + Security (6 layers)

Threat model (dwarvesf/Trail of Bits/Lasso Security): prompt injection via external content · supply chain via `.claude/` (hostile hooks/MCP/CLAUDE.md) · credential exposure (`.env`, SSH, AWS tokens). Full detail: `references/sandbox-and-security.md`.

Six layers, defense in depth:

| Layer | Mechanism | Limitation |
|-------|-----------|------------|
| 1. Permission deny | `settings.json` `permissions.deny` for Read/Edit on `.env`, `~/.ssh/`, `~/.aws/` | Bash bypasses |
| 2. PreToolUse Bash hooks | block `rm -rf`, `git push origin main`, `curl \| bash`, `--no-verify` | regex, not semantic |
| 3. OS sandbox | `/sandbox` per-session (Seatbelt/bubblewrap) | must enable each session |
| 4. UserPromptSubmit secret scan | regex AWS/GitHub/Anthropic/OpenAI tokens, PEM, BIP39 | misses novel formats |
| 5. PostToolUse injection defender | scan Read/WebFetch/Bash output for "ignore previous", "you are now" | pattern-based |
| 6. CLAUDE.md natural lang | rules + reasons | not enforcement |

`enableAllProjectMcpServers: false` in user-global settings — prevents cloned repos from auto-loading hostile MCP.

For cloned-repo paranoia: inspect `.claude/hooks/`, `.claude/settings.local.json`, `.mcp.json`, CLAUDE.md **before** opening with Claude Code.

## Step 8: Verify

Final check — everything created, consistent, within limits:

```bash
echo "=== CLAUDE.md files ==="
find . -name "CLAUDE.md" -not -path "./.claude/*" -exec sh -c 'echo "$(wc -l < "$1") $1"' _ {} \;

echo "=== Prohibition coverage ==="
grep -l "금지\|NEVER\|prohibited\|forbidden" $(find . -name "CLAUDE.md" -not -path "./.claude/*")

echo "=== Hooks registered ==="
jq '.hooks' .claude/settings.local.json 2>/dev/null || echo "(no hooks)"

echo "=== Hook scripts executable ==="
find .claude/scripts -type f -name '*.sh' -perm -u+x -print 2>/dev/null

echo "=== MCP configured ==="
jq '.mcpServers | keys' .mcp.json 2>/dev/null || echo "(no .mcp.json)"

echo "=== ADRs ==="
ls docs/adr/ 2>/dev/null | wc -l

echo "=== Sandbox profile (macOS) ==="
[ -f .claude/sandbox.sb ] && echo "present" || echo "(no sandbox.sb — recommend /sandbox per session)"

echo "=== .gitignore covers harness runtime files ==="
for entry in '.claude/.qg-last-run' '.claude/logs/' '.claude/PROGRESS.json'; do
  grep -qxF "$entry" .gitignore 2>/dev/null && echo "  ✓ $entry" || echo "  ✗ $entry MISSING"
done

echo "=== Drift recheck ==="
bash .claude/scripts/drift-scan.sh
```

**Output**: verification summary with pass/fail per component. Failures → suggest concrete fix (not silent).

## Mode: Codex Multi-Worker Analysis (optional)

After the 8-step bootstrap, large codebases can get a one-shot documentation pass
using an **Opus PM + Codex worker** supervisor pattern (different mechanism from
`harness-loop.sh`, which is single-model autonomous). Use when one Opus turn can't
analyse the codebase, you want layer-by-layer `path:line` friction analysis, or you
want output published into an Obsidian `wiki/harness-engineering/` tree.

Two dispatch modes (both call `codex exec` sync — never `codex-companion --background`):
**Mode A** Claude `run_in_background`; **Mode B** tmux pane via `worker-loop.sh`.
Driver = `scripts/codex-analyze.sh` (`init` / `dispatch` / `spawn` / `verify` / `publish`).

Full mechanism, Mode A/B driver snippets, worker output gates, empirical run data,
produced tree, and "when NOT to use" live in
`references/codex-multi-worker-doctrine.md` (15 principles + operational drivers).

## Merge Mode

When existing CLAUDE.md/AGENTS.md is found:

- Read existing content
- Identify what's covered vs missing
- Propose additions only — **never remove existing prohibitions**
- Highlight conflicts (existing rule contradicts detected pattern)
- Preserve user's voice and language; don't translate Korean rules to English or vice versa

## Minimum Viable Harness (MVH) — phased rollout

**Week 1**: CLAUDE.md (pointer-style ≤50 lines) + pre-commit (Lefthook: fast linter + formatter + type check) + PostToolUse auto-format (Biome/Ruff/gofumpt/rustfmt) + first ADR.

**Week 2–4**: Every agent mistake → test or linter rule (compounding). Plan→approve→execute. E2E tool (Playwright CLI / Hurl / bats-core). Stop hook: tests must pass before done. Session startup (pwd + git log + PROGRESS.json).

**Month 2–3**: Custom linter rules (`ERROR:/WHY:/FIX:/EXAMPLE:` format). ADR↔lint archgate coupling. Strip descriptive docs → replace with tests + ADRs. 6-layer security gates.

**Month 3+**: Multi-linter PostToolUse subprocess delegation. Garbage-collection agents (deterministic rules). Multi-agent (Planner/Generator/Evaluator) at model boundary. Quantitative: PR/day, rework rate.

## Anti-patterns

See `@~/.claude/docs/harness-engineering.md` (section "Anti-patterns") — joint list shared with `harness-project-docs`.

## References

For detailed patterns, read these files from the skill directory:

- `references/hook-templates.md` — full hook scripts with `hookSpecificOutput.additionalContext` JSON pattern, config-protection, security layers
- `references/mcp-catalog.md` — MCP catalog with CLI alternatives and tax warnings
- `references/prohibition-patterns.md` — common prohibitions + AI-specific anti-patterns (any abuse, ghost files, comment floods, 36-40% security vulns)
- `references/language-stacks.md` — per-language fast linter stacks (10 languages: TS/Py/Go/Rust/Swift/Kotlin/Ruby/.NET/Elixir/PHP/Java) + SQL/infra
- `references/sandbox-and-security.md` — 6-layer threat model, `/sandbox` profile, cloned-repo audit, secret rotation runbook, EU AI Act compliance
- `references/measuring-harness.md` — quantitative metrics, baseline measurement, when to strip components, anti-metrics
- `references/plan-mode-and-thinking.md` — Plan Mode + Extended Thinking workflow for harness setup; per-subagent effort calibration; hook gating on effort.level
- `references/codex-multi-worker-doctrine.md` — 15 principles + 12 sources for Opus-PM + Codex-worker supervisor pattern (companion to `scripts/codex-analyze.sh` and `templates/wiki-harness-engineering/`)

## Primary sources

Canonical block in `@~/.claude/docs/harness-engineering.md` (section "Primary sources"). Anthropic Mar 2026, OpenAI, Hashimoto, Thoughtworks, nyosegawa, HumanLayer, IFScale, dwarvesf.
