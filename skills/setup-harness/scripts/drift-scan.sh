#!/usr/bin/env bash
# Drift scan: actually executes the checks from SKILL.md Step 4 and reports findings.
# Run anytime: bash .claude/scripts/drift-scan.sh
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT" || exit 1

echo "=========================================="
echo "Drift scan — $(date -Iseconds)"
echo "=========================================="

fail_count=0
ok() { echo "  ✓ $1"; }
warn() { echo "  ✗ $1"; fail_count=$((fail_count + 1)); }

# 1. CLAUDE.md pointer targets exist (root + folder-level). Links in a folder
#    CLAUDE.md are resolved relative to that folder, not the repo root.
#    NOTE: process substitution (not a pipe) so warn() runs in THIS shell and
#    fail_count actually increments — a `| while` body runs in a subshell and
#    silently drops the count.
echo ""
echo "[1/6] CLAUDE.md pointer targets (root + folder-level)"
mds=$(find . -name CLAUDE.md -not -path './.claude/*' -not -path './node_modules/*' -not -path './.git/*' 2>/dev/null)
if [ -n "$mds" ]; then
  n=0
  while IFS= read -r md; do
    [ -z "$md" ] && continue
    n=$((n + 1))
    dir=$(dirname "$md")
    while IFS= read -r p; do
      [ -z "$p" ] && continue
      case "$p" in http*|/*|\#*) continue ;; esac
      p="${p%%#*}"                       # strip any #anchor
      [ -z "$p" ] && continue
      ( cd "$dir" && [ -e "$p" ] ) || warn "broken pointer in ${md#./}: $p"
    done < <(perl -0777 -pe 's/<!--.*?-->//gs' "$md" 2>/dev/null | grep -oE '\[[^]]+\]\(([^):]+)\)' | sed -E 's/.*\(([^)]+)\)/\1/')
  done <<< "$mds"
  ok "checked $n CLAUDE.md file(s)"
else
  warn "no CLAUDE.md"
fi

# 2. Hook scripts exist and are executable
echo ""
echo "[2/6] Hook scripts"
if [ -f .claude/settings.local.json ]; then
  # process substitution so warn() increments fail_count in this shell
  while IFS= read -r script; do
    [ -z "$script" ] && continue
    if [ ! -f "$script" ]; then
      warn "missing hook script: $script"
    elif [ ! -x "$script" ]; then
      warn "hook script not executable: $script (chmod +x)"
    fi
  done < <(jq -r '.hooks // {} | to_entries[] | .value[]? | .hooks[]? | .command // empty' .claude/settings.local.json | \
    sed -E 's/.*bash +([^ ]+).*/\1/' | \
    sed "s|\${CLAUDE_PROJECT_DIR}|$ROOT|g" | \
    sort -u)
  ok "checked"
else
  warn "no .claude/settings.local.json"
fi

# 3. MCP servers vs declared deps
echo ""
echo "[3/6] MCP ↔ dependency consistency"
if [ ! -f .mcp.json ]; then
  ok "no .mcp.json (skip)"
elif [ -f .mcp.json ]; then
  # process substitution so warn() increments fail_count in this shell
  while IFS= read -r srv; do
    case "$srv" in
      supabase)
        if [ -f package.json ]; then
          grep -q '@supabase/' package.json || warn "supabase MCP but no @supabase/* in package.json"
        elif [ -f requirements.txt ] || [ -f pyproject.toml ]; then
          grep -q 'supabase' requirements.txt pyproject.toml 2>/dev/null || warn "supabase MCP but no supabase in Python deps"
        fi ;;
      sentry)
        grep -q 'sentry' package.json requirements.txt pyproject.toml 2>/dev/null || warn "sentry MCP but no sentry-sdk in deps"
        ;;
    esac
  done < <(jq -r '.mcpServers // {} | keys[]' .mcp.json)
  ok "checked"
fi

# 4. Forbidden patterns in code (exclude harness scripts that legitimately reference these patterns)
echo ""
echo "[4/6] Forbidden patterns"
# git add -A in scripts (exclude .claude/scripts where the pattern is a regex check, not actual usage)
hits=$(find . -path ./node_modules -prune -o -path ./.git -prune -o -path ./.claude/scripts -prune -o -name '*.sh' -print0 2>/dev/null | \
   xargs -0 grep -lE '^[[:space:]]*git +add +(-A|\.|\-\-all)([^a-zA-Z0-9]|$)' 2>/dev/null | head -5)
if [ -n "$hits" ]; then
  warn "'git add -A/.' found in: $hits"
fi

# any abuse (TS)
if [ -f package.json ]; then
  count=$(grep -rE ': *any( |;|,|\)|>)' --include='*.ts' --include='*.tsx' src 2>/dev/null | wc -l | tr -d ' ')
  [ "${count:-0}" -gt 20 ] && warn "high 'any' usage in TS ($count occurrences) — enforce @typescript-eslint/no-explicit-any"
fi

# Source files >300 lines
big=$(find . \( -path ./node_modules -o -path ./.git -o -path ./.venv -o -path ./dist -o -path ./build \) -prune -o \
  \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.go' -o -name '*.rs' \) -print0 2>/dev/null | \
  xargs -0 wc -l 2>/dev/null | awk '$1>300 && $2!="total"{print $2 "("$1")"}' | head -5)
[ -n "$big" ] && warn "files >300 lines: $big"

ok "checked"

# 5. ADR ↔ rule binding
echo ""
echo "[5/6] ADR coverage"
if [ -d docs/adr ]; then
  adr_count=$(find docs/adr -name 'ADR-*.md' -o -name '[0-9]*.md' 2>/dev/null | wc -l | tr -d ' ')
  echo "  $adr_count ADR(s) found"
else
  warn "no docs/adr/ directory — start with /docs/adr/0001-record-architecture-decisions.md"
fi

# 6. Sandbox + security baseline
echo ""
echo "[6/6] Security baseline"
if [ -f .claude/settings.local.json ]; then
  jq -e '.hooks.PreToolUse[]? | select(.matcher=="Bash")' .claude/settings.local.json >/dev/null 2>&1 && \
    ok "PreToolUse(Bash) guard registered" || warn "no PreToolUse(Bash) guard"
  jq -e '.hooks.UserPromptSubmit' .claude/settings.local.json >/dev/null 2>&1 && \
    ok "UserPromptSubmit secret scan registered" || warn "no UserPromptSubmit secret scan"
fi

# .env in .gitignore
if [ -f .gitignore ]; then
  grep -qE '^\.env$|^\.env\*|^\.env\..*' .gitignore || warn ".env not in .gitignore"
fi

echo ""
echo "=========================================="
if [ "$fail_count" -eq 0 ]; then
  echo "PASS — no drift detected"
else
  echo "FAIL — $fail_count drift item(s). Address before merging."
  exit 1
fi
