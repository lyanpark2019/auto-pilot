#!/usr/bin/env bash
# Score current project's harness across 15 dimensions. Output: JSON to .claude/score.json.
# Run anytime: bash .claude/scripts/score-harness.sh
# Used by harness-loop.sh to detect dimensions below target.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$ROOT/.claude/score.json"
mkdir -p "$ROOT/.claude"

# Each scorer returns 0-100. Weighted equally.
score_philosophy() {
  # Heuristic: CLAUDE.md exists + has "Why:" or "이유" column
  [ ! -f CLAUDE.md ] && { echo 0; return; }
  if grep -qE "이유|reason|Why:|WHY:" CLAUDE.md; then echo 95; else echo 60; fi
}

score_claudemd() {
  # Root CLAUDE.md quality ONLY. Folder-level interfaces are scored separately
  # in score_folder_interfaces() — keep this dimension honest so a project with a
  # strong root never silently drops below its root budget.
  [ ! -f CLAUDE.md ] && { echo 0; return; }
  lines=$(wc -l < CLAUDE.md)
  # ≤50 → 100, ≤80 → 85, ≤150 → 60, >150 → 30
  if [ "$lines" -le 50 ]; then echo 100
  elif [ "$lines" -le 80 ]; then echo 85
  elif [ "$lines" -le 150 ]; then echo 60
  else echo 30
  fi
}

score_folder_interfaces() {
  # Coverage of dense/layer folders by substantive CLAUDE.md interfaces.
  # Proportionality: no candidate folders (or tool absent) → 100 (N/A, no penalty).
  # Opt-out: raise FOLDER_THRESHOLD so fewer folders qualify as candidates.
  [ -x "$SELF_DIR/folder-claudemd.sh" ] || { echo 100; return; }
  read -r covered total < <(bash "$SELF_DIR/folder-claudemd.sh" coverage 2>/dev/null || echo "0 0")
  [ "${total:-0}" -eq 0 ] && { echo 100; return; }
  echo $(( covered * 100 / total ))
}

score_hooks() {
  [ ! -f .claude/settings.local.json ] && { echo 0; return; }
  # Score = % of 6 expected events present
  events=$(jq -r '.hooks // {} | keys[]' .claude/settings.local.json 2>/dev/null | sort -u)
  expected="PreToolUse PostToolUse Stop UserPromptSubmit SessionStart PreCompact"
  present=0; total=0
  for e in $expected; do
    total=$((total + 1))
    echo "$events" | grep -qx "$e" && present=$((present + 1))
  done
  echo $(( present * 100 / total ))
}

score_hook_json_format() {
  # Score = does PostToolUse hook emit hookSpecificOutput.additionalContext (vs stdout)?
  [ ! -f .claude/scripts/post-edit-lint.sh ] && { echo 0; return; }
  if grep -q "hookSpecificOutput" .claude/scripts/post-edit-lint.sh; then echo 100; else echo 30; fi
}

score_security() {
  # 6 layers
  layers=0
  [ -f .claude/scripts/guard-bash.sh ] && layers=$((layers + 1))
  [ -f .claude/scripts/block-env-edit.sh ] && layers=$((layers + 1))
  [ -f .claude/scripts/scan-secrets.sh ] && layers=$((layers + 1))
  [ -f .claude/scripts/injection-defender.sh ] && layers=$((layers + 1))
  [ -f .claude/scripts/protect-lint-config.sh ] && layers=$((layers + 1))
  grep -qE "보안|security|금지" CLAUDE.md 2>/dev/null && layers=$((layers + 1))
  echo $(( layers * 100 / 6 ))
}

score_drift() {
  [ ! -x .claude/scripts/drift-scan.sh ] && { echo 0; return; }
  if bash .claude/scripts/drift-scan.sh >/dev/null 2>&1; then echo 100; else echo 50; fi
}

score_linter() {
  # Project-aware: score relative to stack present.
  # No-stack project (no package.json/pyproject/go.mod/Cargo.toml) → not applicable, baseline 90.
  has_stack=0
  [ -f package.json ] || [ -f pyproject.toml ] || [ -f requirements.txt ] || [ -f go.mod ] || [ -f Cargo.toml ] && has_stack=1
  [ "$has_stack" -eq 0 ] && { echo 90; return; }

  pts=0
  ([ -f biome.json ] || [ -f biome.jsonc ]) && pts=$((pts + 30))
  command -v ruff >/dev/null 2>&1 && pts=$((pts + 30))
  command -v gofumpt >/dev/null 2>&1 && pts=$((pts + 20))
  [ -f Cargo.toml ] && grep -q "allow_attributes" Cargo.toml 2>/dev/null && pts=$((pts + 20))
  ([ -f lefthook.yml ] || [ -f .pre-commit-config.yaml ]) && pts=$((pts + 20))
  [ "$pts" -gt 100 ] && pts=100
  # Stack present but no fast linter → baseline 40 (penalty for slow ESLint+Prettier)
  [ "$pts" -eq 0 ] && pts=40
  echo $pts
}

score_adr() {
  [ ! -d docs/adr ] && { echo 30; return; }
  count=$(find docs/adr -name '[0-9]*.md' 2>/dev/null | wc -l | tr -d ' ')
  [ "$count" -ge 3 ] && echo 100 && return
  [ "$count" -ge 1 ] && echo 70 && return
  echo 30
}

score_automation() {
  # bootstrap.sh + drift-scan.sh ship and run
  pts=0
  [ -x .claude/scripts/drift-scan.sh ] && pts=$((pts + 50))
  [ -f .claude/PROGRESS.json ] && pts=$((pts + 25))
  [ -x .claude/scripts/session-start.sh ] && pts=$((pts + 25))
  echo $pts
}

score_idempotency() {
  # Does settings.local.json contain duplicate hooks?
  [ ! -f .claude/settings.local.json ] && { echo 0; return; }
  dups=$(jq '[.hooks // {} | to_entries[] | .value[] | "\(.matcher)|\(.hooks[0].command)"] | group_by(.) | map(select(length>1)) | length' .claude/settings.local.json 2>/dev/null || echo 0)
  [ "${dups:-0}" -eq 0 ] && echo 100 || echo 40
}

score_evals() {
  [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -f "${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/evals/evals.json" ] && echo 95 && return
  [ -f .claude/skills/setup-harness/evals/evals.json ] && echo 95 && return
  echo 70
}

score_gitignore() {
  [ ! -f .gitignore ] && { echo 0; return; }
  pts=0
  grep -qE "^\.env$|^\.env\*" .gitignore && pts=$((pts + 40))
  grep -q ".claude/logs" .gitignore && pts=$((pts + 30))
  grep -q ".claude/PROGRESS.json" .gitignore && pts=$((pts + 30))
  echo $pts
}

score_mcp_hygiene() {
  [ ! -f .mcp.json ] && { echo 95; return; }  # no MCP = clean default
  # Has Playwright MCP for self-testing? penalize
  if jq -e '.mcpServers["playwright"]' .mcp.json >/dev/null 2>&1; then
    grep -q "Playwright CLI" CLAUDE.md 2>/dev/null && echo 80 || echo 50
  else echo 95
  fi
}

score_sandbox() {
  [ -f .claude/sandbox.sb ] && echo 100 && return
  echo 60  # Recommend but not required
}

# Compute all
PHILO=$(score_philosophy)
CLAUDEMD=$(score_claudemd)
FOLDERS=$(score_folder_interfaces)
HOOKS=$(score_hooks)
HOOKFMT=$(score_hook_json_format)
SEC=$(score_security)
DRIFT=$(score_drift)
LINT=$(score_linter)
ADR=$(score_adr)
AUTO=$(score_automation)
IDEM=$(score_idempotency)
EVALS=$(score_evals)
GITI=$(score_gitignore)
MCP=$(score_mcp_hygiene)
SANDBOX=$(score_sandbox)

TOTAL=$(( (PHILO + CLAUDEMD + FOLDERS + HOOKS + HOOKFMT + SEC + DRIFT + LINT + ADR + AUTO + IDEM + EVALS + GITI + MCP + SANDBOX) / 15 ))

cat > "$OUT" <<EOF
{
  "scored_at": "$(date -Iseconds)",
  "total": $TOTAL,
  "dimensions": {
    "philosophy": $PHILO,
    "claudemd": $CLAUDEMD,
    "folder_interfaces": $FOLDERS,
    "hooks_coverage": $HOOKS,
    "hooks_json_format": $HOOKFMT,
    "security": $SEC,
    "drift_detection": $DRIFT,
    "linter": $LINT,
    "adr": $ADR,
    "automation": $AUTO,
    "idempotency": $IDEM,
    "evals": $EVALS,
    "gitignore": $GITI,
    "mcp_hygiene": $MCP,
    "sandbox": $SANDBOX
  }
}
EOF

# Output to stdout for orchestrator
cat "$OUT"
