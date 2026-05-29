#!/usr/bin/env bash
# Bootstrap Claude Code harness in current project.
# Idempotent: re-running merges with existing config, never overwrites.
#
# Usage:
#   bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh           # install
#   DRY_RUN=1 bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/bootstrap.sh # audit-only
#
# Requires: jq, git
set -euo pipefail
DRY_RUN="${DRY_RUN:-0}"
say() { echo "$@"; }
do_cp() { if [ "$DRY_RUN" = "1" ]; then say "    [dry-run] would copy $1 → $2"; else cp "$1" "$2"; chmod +x "$2"; fi; }

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SCRIPTS_DIR="$ROOT/.claude/scripts"
SETTINGS="$ROOT/.claude/settings.local.json"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$DRY_RUN" = "1" ]; then
  echo "==> Bootstrapping harness in: $ROOT (DRY RUN — no changes will be made)"
else
  echo "==> Bootstrapping harness in: $ROOT"
fi

# --- Preflight ---
command -v jq >/dev/null  || { echo "ERROR: jq required (brew install jq / apt install jq)"; exit 1; }
command -v git >/dev/null || { echo "ERROR: git required"; exit 1; }
[ -d "$ROOT/.git" ] || { echo "ERROR: not a git repo: $ROOT"; exit 1; }

# --- Detect stack ---
STACK_PY=0; STACK_NODE=0; STACK_GO=0; STACK_RUST=0; STACK_SWIFT=0; STACK_KOTLIN=0; STACK_RUBY=0; STACK_DOTNET=0
[ -f "$ROOT/pyproject.toml" ] || [ -f "$ROOT/requirements.txt" ] && STACK_PY=1
[ -f "$ROOT/package.json" ] && STACK_NODE=1
[ -f "$ROOT/go.mod" ] && STACK_GO=1
[ -f "$ROOT/Cargo.toml" ] && STACK_RUST=1
[ -f "$ROOT/Package.swift" ] && STACK_SWIFT=1
[ -f "$ROOT/build.gradle.kts" ] || [ -f "$ROOT/build.gradle" ] && STACK_KOTLIN=1
[ -f "$ROOT/Gemfile" ] && STACK_RUBY=1
for _f in "$ROOT"/*.csproj; do [ -e "$_f" ] && STACK_DOTNET=1 && break; done

# Browser app: a Playwright dependency in package.json → wire the E2E smoke Stop hook.
STACK_BROWSER=0
if [ -f "$ROOT/package.json" ] && \
   jq -e '.devDependencies["@playwright/test"] // .dependencies["@playwright/test"] // .devDependencies.playwright // .dependencies.playwright' \
     "$ROOT/package.json" >/dev/null 2>&1; then
  STACK_BROWSER=1
fi

echo "==> Detected: py=$STACK_PY node=$STACK_NODE go=$STACK_GO rust=$STACK_RUST swift=$STACK_SWIFT kotlin=$STACK_KOTLIN ruby=$STACK_RUBY dotnet=$STACK_DOTNET browser=$STACK_BROWSER"

# --- Copy hook scripts ---
[ "$DRY_RUN" = "1" ] || mkdir -p "$SCRIPTS_DIR"
for script in guard-bash.sh block-env-edit.sh protect-lint-config.sh post-edit-lint.sh stop-quality-gate.sh stop-e2e.sh scan-secrets.sh injection-defender.sh session-start.sh pre-compact-save.sh drift-scan.sh score-harness.sh harness-loop.sh verify-harness.sh folder-claudemd.sh budget-guard.sh poll-cost.sh telemetry.sh weekly-metrics.sh track-read.sh verify-gate.sh kill-switch.sh steer.sh commit-on-stop.sh; do
  src="$SKILL_DIR/$script"
  dst="$SCRIPTS_DIR/$script"
  if [ -f "$src" ] && [ ! -f "$dst" ]; then
    do_cp "$src" "$dst"
    [ "$DRY_RUN" = "1" ] || echo "  + $script"
  elif [ -f "$dst" ]; then
    echo "  = $script (exists, skipped)"
  fi
done

# --- Copy subagents and slash commands ---
AGENTS_SRC="$SKILL_DIR/../agents"
COMMANDS_SRC="$SKILL_DIR/../commands"
AGENTS_DST="$ROOT/.claude/agents"
COMMANDS_DST="$ROOT/.claude/commands"

if [ -d "$AGENTS_SRC" ]; then
  [ "$DRY_RUN" = "1" ] || mkdir -p "$AGENTS_DST"
  for f in "$AGENTS_SRC"/*.md; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    if [ ! -f "$AGENTS_DST/$base" ]; then
      if [ "$DRY_RUN" = "1" ]; then
        echo "    [dry-run] would copy agent $base"
      else
        cp "$f" "$AGENTS_DST/$base"
        echo "  + agents/$base"
      fi
    fi
  done
fi

if [ -d "$COMMANDS_SRC" ]; then
  [ "$DRY_RUN" = "1" ] || mkdir -p "$COMMANDS_DST"
  for f in "$COMMANDS_SRC"/*.md; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    if [ ! -f "$COMMANDS_DST/$base" ]; then
      if [ "$DRY_RUN" = "1" ]; then
        echo "    [dry-run] would copy command $base"
      else
        cp "$f" "$COMMANDS_DST/$base"
        echo "  + commands/$base"
      fi
    fi
  done
fi

# --- Merge settings.local.json ---
if [ "$DRY_RUN" != "1" ]; then
  mkdir -p "$(dirname "$SETTINGS")"
  [ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
fi

# Tuple-based dedupe: (event, matcher, command)
NEW_HOOKS=$(cat <<'EOF'
{
  "PreToolUse": [
    {"matcher":"Bash","hooks":[{"type":"command","command":"bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/guard-bash.sh"}]},
    {"matcher":"Write|Edit|MultiEdit","hooks":[{"type":"command","command":"bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/block-env-edit.sh"}]},
    {"matcher":"Write|Edit|MultiEdit","hooks":[{"type":"command","command":"bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/protect-lint-config.sh"}]}
  ],
  "PostToolUse": [
    {"matcher":"Write|Edit|MultiEdit","hooks":[{"type":"command","command":"bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/post-edit-lint.sh"}]},
    {"matcher":"Read|WebFetch|Bash","hooks":[{"type":"command","command":"bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/injection-defender.sh"}]}
  ],
  "Stop": [
    {"matcher":"","hooks":[{"type":"command","command":"bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/stop-quality-gate.sh"}]}
  ],
  "UserPromptSubmit": [
    {"matcher":"","hooks":[{"type":"command","command":"bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/scan-secrets.sh"}]}
  ],
  "SessionStart": [
    {"matcher":"","hooks":[{"type":"command","command":"bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/session-start.sh"}]}
  ],
  "PreCompact": [
    {"matcher":"","hooks":[{"type":"command","command":"bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/pre-compact-save.sh"}]}
  ]
}
EOF
)

# Merge: for each event, for each new entry, append only if (matcher, command) tuple absent
if [ "$DRY_RUN" = "1" ]; then
  echo "==> [dry-run] would merge hooks into $SETTINGS"
else
  jq --argjson new "$NEW_HOOKS" '
    .hooks //= {} |
    reduce ($new | to_entries[]) as $e (.;
      .hooks[$e.key] //= [] |
      reduce $e.value[] as $newEntry (.;
        if (any(.hooks[$e.key][]; .matcher == $newEntry.matcher and (.hooks[0].command == $newEntry.hooks[0].command)))
        then .
        else .hooks[$e.key] += [$newEntry]
        end
      )
    )
  ' "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
  echo "==> Hooks merged into $SETTINGS"
fi

# --- Browser apps: register the E2E smoke Stop hook (tuple-dedupe, same as above) ---
E2E_CMD='bash ${CLAUDE_PROJECT_DIR}/.claude/scripts/stop-e2e.sh'
if [ "$STACK_BROWSER" = "1" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    echo "==> [dry-run] would register stop-e2e.sh as a Stop hook (Playwright detected)"
  else
    jq --arg cmd "$E2E_CMD" '
      .hooks //= {} | .hooks.Stop //= [] |
      if (any(.hooks.Stop[]; .matcher == "" and (.hooks[0].command == $cmd)))
      then .
      else .hooks.Stop += [{"matcher":"","hooks":[{"type":"command","command":$cmd}]}]
      end
    ' "$SETTINGS" > "$SETTINGS.tmp" && mv "$SETTINGS.tmp" "$SETTINGS"
    echo "==> stop-e2e.sh registered as Stop hook (Playwright detected)"
  fi
fi

# --- .gitignore additions ---
GITIGNORE="$ROOT/.gitignore"
if [ "$DRY_RUN" = "1" ]; then
  echo "==> [dry-run] would add to .gitignore: .claude runtime files + .env*"
else
  touch "$GITIGNORE"
  for entry in '.claude/.qg-last-run' '.claude/logs/' '.claude/PROGRESS.json' '.env' '.env.local' '.env.*.local'; do
    grep -qxF "$entry" "$GITIGNORE" || echo "$entry" >> "$GITIGNORE"
  done
  echo "==> .gitignore updated"
fi

# --- Create empty PROGRESS.json (JSON > Markdown for session continuity) ---
PROGRESS="$ROOT/.claude/PROGRESS.json"
if [ "$DRY_RUN" = "1" ]; then
  [ -f "$PROGRESS" ] || echo "==> [dry-run] would create $PROGRESS"
else
  [ -f "$PROGRESS" ] || echo '{"current_task":"","completed":[],"next":[],"notes":""}' > "$PROGRESS"
fi

# --- CLAUDE.md scaffold (only if absent) ---
CLAUDE_MD="$ROOT/CLAUDE.md"
if [ ! -f "$CLAUDE_MD" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    echo "==> [dry-run] would create CLAUDE.md from template"
  else
    cp "$SKILL_DIR/../templates/CLAUDE.md.template" "$CLAUDE_MD" 2>/dev/null || true
    echo "==> CLAUDE.md scaffold created (edit before commit)"
  fi
else
  echo "==> CLAUDE.md exists, merge mode — edit manually"
fi

# --- Folder-level CLAUDE.md interfaces for dense/layer folders (only if absent) ---
# Call the source script ($SKILL_DIR), not the project copy — the copy may not
# exist yet under DRY_RUN. The script targets CLAUDE_PROJECT_DIR regardless of
# where it is invoked from.
FCM_SRC="$SKILL_DIR/folder-claudemd.sh"
if [ -f "$FCM_SRC" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    out=$(CLAUDE_PROJECT_DIR="$ROOT" DRY_RUN=1 bash "$FCM_SRC" scaffold 2>/dev/null || true)
    [ -n "$out" ] && { echo "==> [dry-run] folder-level CLAUDE.md:"; echo "$out"; }
  else
    out=$(CLAUDE_PROJECT_DIR="$ROOT" bash "$FCM_SRC" scaffold 2>/dev/null || true)
    [ -n "$out" ] && { echo "==> Folder-level CLAUDE.md:"; echo "$out"; }
  fi
fi

# --- ADR directory ---
if [ "$DRY_RUN" = "1" ]; then
  [ -f "$ROOT/docs/adr/0001-record-architecture-decisions.md" ] || echo "==> [dry-run] would scaffold docs/adr/0001-record-architecture-decisions.md"
else
  mkdir -p "$ROOT/docs/adr"
  [ -f "$ROOT/docs/adr/0001-record-architecture-decisions.md" ] || \
    cp "$SKILL_DIR/../templates/ADR-template.md" "$ROOT/docs/adr/0001-record-architecture-decisions.md" 2>/dev/null || true
fi

# --- AGENTS.md (Codex/multi-tool) — only if .codex/ or AGENTS.md absent ---
AGENTS_MD="$ROOT/AGENTS.md"
HAS_CODEX=0
[ -d "$ROOT/.codex" ] && HAS_CODEX=1
if [ "$HAS_CODEX" = "1" ] && [ ! -f "$AGENTS_MD" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    echo "==> [dry-run] would scaffold AGENTS.md (Codex detected)"
  else
    cp "$SKILL_DIR/../templates/AGENTS.md.template" "$AGENTS_MD" 2>/dev/null || true
    echo "==> AGENTS.md scaffolded (Codex coexistence)"
  fi
fi

# --- Codex hooks.json — only if .codex/ exists ---
CODEX_HOOKS="$ROOT/.codex/hooks.json"
if [ "$HAS_CODEX" = "1" ] && [ ! -f "$CODEX_HOOKS" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    echo "==> [dry-run] would scaffold .codex/hooks.json"
  else
    cp "$SKILL_DIR/../templates/codex-hooks.json.template" "$CODEX_HOOKS" 2>/dev/null || true
    echo "==> .codex/hooks.json scaffolded (Bash-only Codex coverage)"
  fi
fi

# --- Sandbox profile (macOS) — recommendation copy ---
SANDBOX="$ROOT/.claude/sandbox.sb"
if [ ! -f "$SANDBOX" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    echo "==> [dry-run] would copy sandbox.sb (run /sandbox per session to activate)"
  else
    cp "$SKILL_DIR/../templates/sandbox.sb.template" "$SANDBOX" 2>/dev/null && \
      echo "==> .claude/sandbox.sb installed (activate per-session: /sandbox)"
  fi
fi

# --- Lefthook scaffold — only if stack detected + no existing config ---
STACK_DETECTED=0
[ "$STACK_PY" = "1" ] || [ "$STACK_NODE" = "1" ] || [ "$STACK_GO" = "1" ] || [ "$STACK_RUST" = "1" ] && STACK_DETECTED=1
if [ "$STACK_DETECTED" = "1" ] && [ ! -f "$ROOT/lefthook.yml" ] && [ ! -f "$ROOT/.pre-commit-config.yaml" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    echo "==> [dry-run] would scaffold lefthook.yml (stack detected: install lefthook for pre-commit speed)"
  else
    cp "$SKILL_DIR/../templates/lefthook.yml.template" "$ROOT/lefthook.yml" 2>/dev/null && \
      echo "==> lefthook.yml scaffolded (install: brew install lefthook && lefthook install)"
  fi
fi

echo ""
echo "==> Done. Next steps:"
echo "  1. Edit CLAUDE.md (≤50 lines, pointer-style, prohibitions with reasons)"
echo "  2. Run /sandbox in your next Claude Code session for OS-level isolation"
echo "  3. Commit: .claude/scripts/, .claude/settings.local.json, CLAUDE.md, docs/adr/, .gitignore"
echo "  4. Run drift scan: bash .claude/scripts/drift-scan.sh"
