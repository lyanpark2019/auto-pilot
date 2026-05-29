#!/usr/bin/env bats
# Unit tests for arl-helpers.sh. Run: bats tests/arl-helpers.bats

setup() {
  HELPERS="${BATS_TEST_DIRNAME}/../scripts/arl-helpers.sh"
  # shellcheck source=/dev/null
  source "$HELPERS"
  WORK="$(mktemp -d)"
  cd "$WORK"
}

teardown() {
  cd /
  rm -rf "$WORK"
}

_init_repo() {
  git init -q
  git config user.email a@b.c
  git config user.name t
  git commit -q --allow-empty -m init
  git branch -M main
}

# --- static -------------------------------------------------------------

@test "script passes bash -n syntax check" {
  run bash -n "$HELPERS"
  [ "$status" -eq 0 ]
}

@test "script passes shellcheck (style+errors)" {
  command -v shellcheck >/dev/null || skip "shellcheck not installed"
  run shellcheck -S style "$HELPERS"
  [ "$status" -eq 0 ]
}

@test "worktree_path: emits convention path" {
  run arl_worktree_path foo
  [ "$status" -eq 0 ]
  [ "$output" = ".worktrees/quality-foo" ]
}

# --- arl_conflict_markers -----------------------------------------------

@test "conflict_markers: clean tree exits 0 with no output" {
  mkdir d; printf 'hello\n' > d/a.txt
  run arl_conflict_markers d
  [ "$status" -eq 0 ]
  [ -z "$output" ]
}

@test "conflict_markers: detects markers" {
  mkdir d; printf '<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> b\n' > d/a.txt
  run arl_conflict_markers d
  [ "$status" -eq 0 ]
  [[ "$output" == *"<<<<<<<"* ]]
}

# --- arl_ahead_behind ----------------------------------------------------

@test "ahead_behind: no upstream degrades gracefully" {
  _init_repo
  run arl_ahead_behind
  [ "$status" -eq 0 ]
  [[ "$output" == *"no upstream"* ]]
}

# --- arl_repo_size_ok ----------------------------------------------------

@test "repo_size_ok: true when count >= threshold" {
  mkdir src; for i in 1 2 3 4 5; do : > "src/f$i"; done
  run arl_repo_size_ok src 3
  [ "$status" -eq 0 ]
}

@test "repo_size_ok: false when count < threshold" {
  mkdir src; : > src/only
  run arl_repo_size_ok src 10
  [ "$status" -eq 1 ]
}

@test "repo_size_ok: missing src_dir arg returns 2" {
  run arl_repo_size_ok ""
  [ "$status" -eq 2 ]
}

# --- arl_parse_scope_files ----------------------------------------------

@test "parse_scope_files: block list form" {
  cat > c.md <<'EOF'
---
scope_files:
  - app/foo.py
  - app/bar.py
---
body
EOF
  run arl_parse_scope_files c.md
  [ "$status" -eq 0 ]
  [ "${lines[0]}" = "app/foo.py" ]
  [ "${lines[1]}" = "app/bar.py" ]
  [ "${#lines[@]}" -eq 2 ]
}

@test "parse_scope_files: inline array form" {
  printf 'scope_files: [a.py, b.py, c.py]\n' > c.md
  run arl_parse_scope_files c.md
  [ "$status" -eq 0 ]
  [ "${#lines[@]}" -eq 3 ]
  [ "${lines[0]}" = "a.py" ]
  [ "${lines[2]}" = "c.py" ]
}

@test "parse_scope_files: missing file returns 2" {
  run arl_parse_scope_files nope.md
  [ "$status" -eq 2 ]
}

# --- arl_contract_path ---------------------------------------------------

@test "contract_path: resolves by slug glob" {
  mkdir -p .planning/quality/contracts
  : > .planning/quality/contracts/contract-001-fix-auth.md
  run arl_contract_path fix-auth
  [ "$status" -eq 0 ]
  [[ "$output" == *"contract-001-fix-auth.md" ]]
}

@test "contract_path: missing slug returns 1" {
  mkdir -p .planning/quality/contracts
  run arl_contract_path ghost
  [ "$status" -eq 1 ]
}

# --- arl_conflict_groups -------------------------------------------------

@test "conflict_groups: shared file groups together, disjoint separate" {
  mkdir -p .planning/quality/contracts
  cd .planning/quality/contracts
  printf 'scope_files:\n  - app/a.py\n' > contract-001-aa.md
  printf 'scope_files:\n  - app/a.py\n  - app/b.py\n' > contract-002-bb.md
  printf 'scope_files:\n  - lib/z.py\n' > contract-003-cc.md
  cd "$WORK"
  run arl_conflict_groups .planning/quality/contracts
  [ "$status" -eq 0 ]
  # aa and bb share app/a.py -> same line; cc alone
  local grouped="" alone=""
  for l in "${lines[@]}"; do
    case "$l" in *aa*bb*|*bb*aa*) grouped="$l";; *cc*) alone="$l";; esac
  done
  [ -n "$grouped" ]
  [ -n "$alone" ]
  [[ "$alone" != *aa* ]]
}

# --- arl_worktree_ensure -------------------------------------------------

@test "worktree_ensure: fresh create on quality/<slug>" {
  _init_repo
  run bash -c "source '$HELPERS'; arl_worktree_ensure foo main >/dev/null 2>&1 && git branch --show-current"
  [ "$status" -eq 0 ]
  [ "$output" = "quality/foo" ]
}

@test "worktree_ensure: reuse existing worktree (idempotent)" {
  _init_repo
  arl_worktree_ensure foo main >/dev/null 2>&1
  cd "$WORK"
  run bash -c "source '$HELPERS'; arl_worktree_ensure foo main >/dev/null 2>&1 && pwd"
  [ "$status" -eq 0 ]
  [[ "$output" == *".worktrees/quality-foo" ]]
}

@test "worktree_ensure: aborts on wrong branch in existing worktree" {
  _init_repo
  git branch other
  git worktree add .worktrees/quality-foo other >/dev/null 2>&1
  run bash -c "source '$HELPERS'; arl_worktree_ensure foo main"
  [ "$status" -ne 0 ]
}

@test "worktree_ensure: missing slug returns 2" {
  _init_repo
  run arl_worktree_ensure ""
  [ "$status" -eq 2 ]
}

@test "worktree_cleanup: removes worktree despite untracked files" {
  _init_repo
  arl_worktree_ensure foo main >/dev/null 2>&1   # cwd now in worktree
  : > junk.untracked                              # simulate pytest __pycache__
  cd "$WORK"
  run arl_worktree_cleanup foo
  [ "$status" -eq 0 ]
  run git worktree list
  [[ "$output" != *"quality-foo"* ]]
}

# --- arl_pr_create_idempotent (gh mocked) -------------------------------

# arg: 1 = an open PR exists (gh pr list prints a number), 0 = none (prints nothing)
_mock_gh() {
  local exists="$1"
  mkdir -p "$WORK/bin"
  cat > "$WORK/bin/gh" <<EOF
#!/usr/bin/env bash
echo "gh \$*" >> "$WORK/gh.log"
if [ "\$1" = "pr" ] && [ "\$2" = "list" ]; then
  $([ "$exists" = "1" ] && echo 'printf "7\n"' || echo 'printf ""')
fi
exit 0
EOF
  chmod +x "$WORK/bin/gh"
  PATH="$WORK/bin:$PATH"
}

@test "pr_create_idempotent: skips create when PR exists" {
  _mock_gh 1   # gh pr list returns a number -> PR exists
  : > contract.md
  run arl_pr_create_idempotent foo contract.md main
  [ "$status" -eq 0 ]
  run cat "$WORK/gh.log"
  [[ "$output" == *"pr list"* ]]
  [[ "$output" != *"pr create"* ]]
}

@test "pr_create_idempotent: creates when PR absent" {
  _mock_gh 0   # gh pr list returns empty -> no PR
  : > contract.md
  run arl_pr_create_idempotent foo contract.md main
  [ "$status" -eq 0 ]
  run cat "$WORK/gh.log"
  [[ "$output" == *"pr create"* ]]
}

@test "pr_create_idempotent: missing args returns 2" {
  run arl_pr_create_idempotent foo ""
  [ "$status" -eq 2 ]
}

# --- arl_local_merge (git mocked for call-order) ------------------------

@test "local_merge: fetches worker branch before merging" {
  mkdir -p "$WORK/bin"
  cat > "$WORK/bin/git" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$WORK/git.log"
exit 0
EOF
  chmod +x "$WORK/bin/git"
  PATH="$WORK/bin:$PATH" run arl_local_merge foo
  [ "$status" -eq 0 ]
  run cat "$WORK/git.log"
  # first recorded git call must be the fetch of the worker branch
  [ "${lines[0]}" = "fetch origin quality/foo" ]
  [[ "$output" == *"merge --ff-only origin/quality/foo"* ]]
}

@test "local_merge: missing slug returns 2" {
  run arl_local_merge ""
  [ "$status" -eq 2 ]
}
