#!/usr/bin/env bats
# Integration tests for setup-harness CLI tools against a temp git repo.
# Fork scripts (tmux/claude/codex execution) are covered only at their
# arg-guard / scaffold boundary — the actual fork is out of scope (needs a
# live tmux/claude/codex; documented limitation).

setup() {
  S="${BATS_TEST_DIRNAME}/../scripts"
  PROJ="$BATS_TEST_TMPDIR/proj"
  mkdir -p "$PROJ"
  git -C "$PROJ" init -q
  git -C "$PROJ" config user.email t@t
  git -C "$PROJ" config user.name t
  echo "# proj" > "$PROJ/README.md"
  git -C "$PROJ" add -A && git -C "$PROJ" commit -qm init
  export CLAUDE_PROJECT_DIR="$PROJ"
}

# ---------- score-harness.sh ----------
@test "score-harness: emits valid JSON with total + dimensions" {
  run bash "$S/score-harness.sh"
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.total and .dimensions and .scored_at' >/dev/null
}
@test "score-harness: total is numeric 0..100" {
  run bash "$S/score-harness.sh"
  t=$(echo "$output" | jq -r '.total')
  [ "$t" -ge 0 ] && [ "$t" -le 100 ]
}

# ---------- bootstrap.sh (dry-run must not error, must not commit) ----------
@test "bootstrap: DRY_RUN exits 0 and leaves tree clean" {
  DRY_RUN=1 run bash "$S/bootstrap.sh"
  [ "$status" -eq 0 ]
  [ -z "$(git -C "$PROJ" status --porcelain)" ]
}

# ---------- drift-scan.sh ----------
@test "drift-scan: runs and prints the 6-check banner" {
  run bash "$S/drift-scan.sh"
  [[ "$output" == *"=="* ]]
  [[ "$output" == *"[1/6]"* || "$output" == *"/6]"* ]]
}

# ---------- folder-claudemd.sh ----------
@test "folder-claudemd: candidates mode exits 0" {
  run bash "$S/folder-claudemd.sh" candidates
  [ "$status" -eq 0 ]
}

# ---------- verify-harness.sh ----------
@test "verify-harness: runs and prints a verification banner" {
  run bash "$S/verify-harness.sh"
  [[ "$output" == *"Verification"* || "$output" == *"=="* ]]
}

# ---------- check_doc_drift.sh ----------
@test "check_doc_drift: runs against a repo without crashing" {
  run bash "$S/check_doc_drift.sh"
  # 0 = no drift, nonzero = drift found; both are valid "ran" outcomes.
  [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
}

# ---------- install-drift-hook.sh ----------
@test "install-drift-hook: copies the drift checker into the target repo" {
  run bash "$S/install-drift-hook.sh" "$PROJ"
  [ "$status" -eq 0 ]
  [ -f "$PROJ/scripts/quality/check_doc_drift.sh" ] || [ -f "$PROJ/.claude/scripts/check_doc_drift.sh" ]
}

# ---------- codex-analyze.sh (init scaffolds; no codex fork) ----------
@test "codex-analyze: init scaffolds planning dirs without forking codex" {
  run bash "$S/codex-analyze.sh" init "$PROJ" 3
  [ "$status" -eq 0 ]
  [ -d "$PROJ/.planning/harness-rewrite/inbox" ]
  [ -d "$PROJ/.planning/harness-rewrite/outbox" ]
}

# ---------- fork scripts: arg-guard only (no actual fork) ----------
@test "spawn-tmux: missing args exits nonzero (guarded before fork)" {
  run bash "$S/spawn-tmux.sh"
  [ "$status" -ne 0 ]
}
@test "worker-loop: missing WORKER_ID exits nonzero (guarded before fork)" {
  run timeout 5 bash "$S/worker-loop.sh"
  [ "$status" -ne 0 ]
}
