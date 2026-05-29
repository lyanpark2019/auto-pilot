#!/usr/bin/env bash
# Final verification agent. Runs after loop hits target.
# Independent of score-harness.sh — verifies functionally that the harness actually works.
# Catches: scores high but hooks don't trigger / scripts non-executable / JSON malformed / drift after install.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT" || exit 1
fails=0
warns=0

ok()   { echo "  ✓ $1"; }
fail() { echo "  ✗ FAIL: $1"; fails=$((fails + 1)); }
warn() { echo "  ⚠ WARN: $1"; warns=$((warns + 1)); }

echo "=========================================="
echo "Final Verification — $(date -Iseconds)"
echo "=========================================="

# --- A. Script integrity ---
echo ""
echo "[A] Script integrity"
if [ -d .claude/scripts ]; then
  for s in .claude/scripts/*.sh; do
    [ -f "$s" ] || continue
    [ -x "$s" ] || fail "non-executable: $s"
    bash -n "$s" 2>/dev/null || fail "syntax error: $s"
  done
  ok "all scripts syntactically valid + executable"
else
  fail "no .claude/scripts dir"
fi

# --- B. Hook registration ---
echo ""
echo "[B] Hook registration"
if [ -f .claude/settings.local.json ]; then
  jq -e '.hooks' .claude/settings.local.json >/dev/null 2>&1 || fail "settings.local.json has no .hooks key"
  for evt in PreToolUse PostToolUse Stop UserPromptSubmit SessionStart PreCompact; do
    jq -e ".hooks.$evt" .claude/settings.local.json >/dev/null 2>&1 || warn "missing event: $evt"
  done
  # Idempotency: no duplicate (matcher, command) tuples
  dups=$(jq '[.hooks // {} | to_entries[] | .value[] | "\(.matcher)|\(.hooks[0].command)"] | group_by(.) | map(select(length>1)) | length' .claude/settings.local.json)
  [ "${dups:-0}" -eq 0 ] && ok "no duplicate hooks" || fail "$dups duplicate hook(s) detected"
else
  fail "no settings.local.json"
fi

# --- C. Functional hook tests ---
echo ""
echo "[C] Functional hook tests (sandbox)"
test_hook() {
  local script="$1" payload="$2" expect_exit="$3" label="$4"
  [ -x "$script" ] || { fail "missing $script"; return; }
  actual=$(echo "$payload" | bash "$script" >/dev/null 2>&1; echo $?)
  if [ "$actual" = "$expect_exit" ]; then ok "$label"
  else fail "$label (expected exit=$expect_exit, got $actual)"
  fi
}

# guard-bash blocks bypass attempt
GUARD=".claude/scripts/guard-bash.sh"
[ -x "$GUARD" ] && {
  bypass_cmd="git $(echo 'commit') --no-verify -m x"
  test_hook "$GUARD" "{\"tool_input\":{\"command\":\"$bypass_cmd\"}}" "2" "guard-bash blocks --no-verify"
  test_hook "$GUARD" '{"tool_input":{"command":"ls"}}' "0" "guard-bash allows benign"
}

# block-env-edit blocks .env
ENVB=".claude/scripts/block-env-edit.sh"
[ -x "$ENVB" ] && {
  test_hook "$ENVB" '{"tool_input":{"file_path":".env"}}' "2" "block-env-edit blocks .env"
  test_hook "$ENVB" '{"tool_input":{"file_path":"src/main.py"}}' "0" "block-env-edit allows src"
}

# protect-lint-config blocks pyproject.toml
PLINT=".claude/scripts/protect-lint-config.sh"
[ -x "$PLINT" ] && {
  test_hook "$PLINT" '{"tool_input":{"file_path":"pyproject.toml"}}' "2" "protect-lint blocks pyproject.toml"
}

# scan-secrets blocks known AWS pattern
SCAN=".claude/scripts/scan-secrets.sh"
[ -x "$SCAN" ] && {
  test_hook "$SCAN" '{"prompt":"key is AKIAIOSFODNN7EXAMPLE"}' "2" "scan-secrets blocks AWS key"
  test_hook "$SCAN" '{"prompt":"hello"}' "0" "scan-secrets allows benign"
}

# --- C2. folder-claudemd anti-gaming logic ---
echo ""
echo "[C2] folder-claudemd substantive-coverage logic"
FCM="$ROOT/.claude/scripts/folder-claudemd.sh"
if [ -x "$FCM" ]; then
  tmp=$(mktemp -d)
  mkdir -p "$tmp/mod"
  for i in $(seq 1 11); do echo "x=$i" > "$tmp/mod/f$i.py"; done
  # CLAUDE_PROJECT_DIR pinned to tmp so coverage scans the sandbox, not the real repo.
  cov() { CLAUDE_PROJECT_DIR="$tmp" bash "$FCM" coverage 2>/dev/null; }
  c1=$(cov)                                              # 1. no interface → uncovered
  CLAUDE_PROJECT_DIR="$tmp" bash "$FCM" scaffold >/dev/null 2>&1
  c2=$(cov)                                              # 2. stub present, placeholders unfilled → still uncovered
  printf '# mod\n## 금지\n- **no raw sql** — ADR-002\n' > "$tmp/mod/CLAUDE.md"
  c3=$(cov)                                              # 3. real rules → covered
  res="$c1|$c2|$c3"
  [ "$res" = "0 1|0 1|1 1" ] \
    && ok "folder-claudemd: empty stub stays uncovered, filled file counts ($res)" \
    || fail "folder-claudemd coverage logic wrong: got '$res' (expected '0 1|0 1|1 1')"
  rm -rf "$tmp"
else
  warn "folder-claudemd.sh not installed — skipping anti-gaming test"
fi

# --- C3. stop-e2e safe no-op ---
echo ""
echo "[C3] stop-e2e safe no-op (must never block when irrelevant)"
E2E="$ROOT/.claude/scripts/stop-e2e.sh"
if [ -x "$E2E" ]; then
  etmp=$(mktemp -d)   # empty dir: no package.json
  a1=$(echo '{"stop_hook_active":true}' | CLAUDE_PROJECT_DIR="$etmp" bash "$E2E" >/dev/null 2>&1; echo $?)
  a2=$(echo '{}' | CLAUDE_PROJECT_DIR="$etmp" bash "$E2E" >/dev/null 2>&1; echo $?)
  [ "$a1" = "0" ] && ok "stop-e2e respects stop_hook_active (exit 0)" || fail "stop-e2e stop_hook_active (got $a1)"
  [ "$a2" = "0" ] && ok "stop-e2e no-ops without package.json (exit 0)" || fail "stop-e2e non-browser no-op (got $a2)"
  rm -rf "$etmp"
else
  warn "stop-e2e.sh not installed — skipping no-op test"
fi

# --- D. JSON output format ---
echo ""
echo "[D] PostToolUse JSON format"
if [ -x .claude/scripts/post-edit-lint.sh ]; then
  grep -q "hookSpecificOutput" .claude/scripts/post-edit-lint.sh && \
    ok "post-edit-lint uses hookSpecificOutput.additionalContext" || \
    fail "post-edit-lint missing hookSpecificOutput — feedback won't reach agent"
fi
if [ -x .claude/scripts/injection-defender.sh ]; then
  grep -q "hookSpecificOutput" .claude/scripts/injection-defender.sh && \
    ok "injection-defender uses hookSpecificOutput.additionalContext"
fi

# --- E. CLAUDE.md compliance ---
echo ""
echo "[E] CLAUDE.md compliance"
if [ -f CLAUDE.md ]; then
  lines=$(wc -l < CLAUDE.md)
  if [ "$lines" -le 80 ]; then ok "CLAUDE.md=$lines lines (within 80)"
  elif [ "$lines" -le 150 ]; then warn "CLAUDE.md=$lines lines (>80 target, <150 hard cap)"
  else fail "CLAUDE.md=$lines lines exceeds IFScale degradation threshold"
  fi
  grep -qE "이유|reason|Why:|WHY:" CLAUDE.md && ok "prohibitions have reasons" || warn "prohibitions lack 'why' column"
fi

# --- F. Drift scan ---
echo ""
echo "[F] Drift scan"
if [ -x .claude/scripts/drift-scan.sh ]; then
  if bash .claude/scripts/drift-scan.sh >/tmp/.drift.$$ 2>&1; then
    ok "drift-scan PASS"
  else
    fail "drift-scan FAIL — see output:"
    tail -20 /tmp/.drift.$$ | sed 's/^/    /'
  fi
  rm -f /tmp/.drift.$$
fi

# --- G. Score reconciliation ---
echo ""
echo "[G] Score reconciliation"
if [ -f .claude/score.json ]; then
  total=$(jq -r '.total' .claude/score.json)
  ok "current score: $total"
  jq -r '.dimensions | to_entries[] | "    \(.key): \(.value)"' .claude/score.json
fi

# --- Verdict ---
echo ""
echo "=========================================="
if [ "$fails" -eq 0 ]; then
  echo "VERIFIED — $warns warning(s)"
  exit 0
else
  echo "FAILED — $fails error(s), $warns warning(s)"
  exit 1
fi
