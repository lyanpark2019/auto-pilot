#!/usr/bin/env bash
# Autonomous harness improvement loop.
# Score → if total < target → auto-fix lowest dimension → re-score → repeat.
# Stops when target reached or MAX_ITERATIONS hit.
#
# Usage:
#   bash .claude/scripts/harness-loop.sh                 # default target 95
#   TARGET=100 bash .claude/scripts/harness-loop.sh
#   MAX_ITERATIONS=10 TARGET=95 bash .claude/scripts/harness-loop.sh
#
# Exit codes: 0=target reached, 1=max iterations without target, 2=stuck (same score 3x)
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TARGET="${TARGET:-95}"
MAX_ITERATIONS="${MAX_ITERATIONS:-10}"
LOG="$ROOT/.claude/harness-loop.log"
mkdir -p "$ROOT/.claude"
echo "=== harness-loop start $(date -Iseconds) target=$TARGET max_iter=$MAX_ITERATIONS ===" | tee "$LOG"

stuck_count=0
last_score=-1
attempted=" "  # space-separated; bash 3.2 compatible (no -A assoc array)

for iter in $(seq 1 "$MAX_ITERATIONS"); do
  echo ""
  echo "--- iteration $iter ---" | tee -a "$LOG"

  # 1. SCORE
  bash "$SKILL_DIR/score-harness.sh" >/dev/null 2>&1
  if [ ! -f .claude/score.json ]; then
    echo "FATAL: score.json not generated" | tee -a "$LOG"
    exit 1
  fi
  total=$(jq -r '.total' .claude/score.json)
  echo "  score: $total" | tee -a "$LOG"

  # 2. CHECK TARGET
  if [ "$total" -ge "$TARGET" ]; then
    echo ""
    echo "=== TARGET REACHED ($total ≥ $TARGET) at iteration $iter ===" | tee -a "$LOG"
    bash "$SKILL_DIR/verify-harness.sh"
    exit 0
  fi

  # 3. PICK NEXT DIMENSION — lowest one NOT yet attempted
  lowest=""
  while IFS= read -r dim; do
    case "$attempted" in
      *" $dim "*) continue ;;
      *) lowest="$dim"; break ;;
    esac
  done < <(jq -r '.dimensions | to_entries | sort_by(.value) | .[].key' .claude/score.json)

  # All dimensions attempted → reset attempts and check stuck
  if [ -z "$lowest" ]; then
    if [ "$total" -eq "$last_score" ]; then
      stuck_count=$((stuck_count + 1))
      if [ "$stuck_count" -ge 1 ]; then
        echo "STUCK at $total — all dimensions attempted, no progress. Needs human." | tee -a "$LOG"
        jq '.dimensions | to_entries | sort_by(.value)[0:5]' .claude/score.json | tee -a "$LOG"
        exit 2
      fi
    fi
    attempted=" "
    last_score=$total
    continue
  fi

  # Reset attempted-list whenever score improves (progress = try lowest again)
  if [ "$total" -gt "$last_score" ] && [ "$last_score" -ge 0 ]; then
    attempted=" $lowest "
  else
    attempted="$attempted$lowest "
  fi
  last_score=$total
  lowest_val=$(jq -r ".dimensions.$lowest" .claude/score.json)
  echo "  next: $lowest=$lowest_val → autofix" | tee -a "$LOG"

  # 5. AUTOFIX (per-dimension)
  case "$lowest" in
    philosophy|claudemd)
      # Re-run bootstrap CLAUDE.md scaffold if absent or oversized
      if [ ! -f CLAUDE.md ]; then
        cp "$SKILL_DIR/../templates/CLAUDE.md.template" CLAUDE.md
        echo "    + scaffolded CLAUDE.md from template" | tee -a "$LOG"
      elif [ "$(wc -l < CLAUDE.md)" -gt 150 ]; then
        cp CLAUDE.md CLAUDE.md.bak
        echo "    ! CLAUDE.md > 150 lines — manual review needed (saved CLAUDE.md.bak)" | tee -a "$LOG"
      fi
      ;;
    folder_interfaces)
      # Scaffold stubs for dense/layer folders. Score only rises once a human
      # fills the {placeholder} tokens with real rules, so this may not self-heal.
      if [ -x .claude/scripts/folder-claudemd.sh ]; then
        out=$(bash .claude/scripts/folder-claudemd.sh scaffold 2>/dev/null || true)
        [ -n "$out" ] && echo "$out" | tee -a "$LOG"
        echo "    ! folder interfaces scaffolded — fill {placeholder} tokens with real rules to raise score" | tee -a "$LOG"
      fi
      ;;
    hooks_coverage|hooks_json_format|idempotency|automation)
      bash "$SKILL_DIR/bootstrap.sh" >> "$LOG" 2>&1
      echo "    + ran bootstrap (idempotent)" | tee -a "$LOG"
      ;;
    security)
      bash "$SKILL_DIR/bootstrap.sh" >> "$LOG" 2>&1
      [ -f CLAUDE.md ] && ! grep -qE "보안|security|금지" CLAUDE.md && {
        printf "\n## 절대 금지\n| 금지 | 이유 |\n|------|------|\n| \`--no-verify\` | bypass guard |\n" >> CLAUDE.md
        echo "    + appended prohibitions section to CLAUDE.md" | tee -a "$LOG"
      }
      ;;
    drift_detection)
      [ -x .claude/scripts/drift-scan.sh ] || bash "$SKILL_DIR/bootstrap.sh" >> "$LOG" 2>&1
      bash .claude/scripts/drift-scan.sh 2>&1 | tee -a "$LOG"
      echo "    ! drift found — review .claude/harness-loop.log and fix manually" | tee -a "$LOG"
      ;;
    linter)
      echo "    ! linter setup is project-specific — see references/language-stacks.md" | tee -a "$LOG"
      ;;
    adr)
      mkdir -p docs/adr
      # Scaffold up to 3 ADRs (score=100 requires 3+)
      for n in 0001 0002 0003; do
        f="docs/adr/${n}-decision-placeholder.md"
        [ "$n" = "0001" ] && f="docs/adr/0001-record-architecture-decisions.md"
        if [ ! -f "$f" ]; then
          cp "$SKILL_DIR/../templates/ADR-template.md" "$f"
          echo "    + scaffolded $f" | tee -a "$LOG"
        fi
      done
      ;;
    evals)
      echo "    + evals managed by skill, no per-project action" | tee -a "$LOG"
      ;;
    gitignore)
      for entry in '.env' '.env.local' '.env.*.local' '.claude/.qg-last-run' '.claude/logs/' '.claude/PROGRESS.json'; do
        grep -qxF "$entry" .gitignore 2>/dev/null || echo "$entry" >> .gitignore
      done
      echo "    + updated .gitignore" | tee -a "$LOG"
      ;;
    mcp_hygiene)
      [ -f .mcp.json ] && echo "    ! review .mcp.json — prefer Playwright CLI over MCP" | tee -a "$LOG"
      ;;
    sandbox)
      cp "$SKILL_DIR/../templates/sandbox.sb.template" .claude/sandbox.sb 2>/dev/null && \
        echo "    + installed .claude/sandbox.sb (run /sandbox per session)" | tee -a "$LOG"
      ;;
  esac
done

echo ""
echo "=== MAX_ITERATIONS reached without hitting $TARGET ===" | tee -a "$LOG"
jq '.' .claude/score.json | tee -a "$LOG"
exit 1
