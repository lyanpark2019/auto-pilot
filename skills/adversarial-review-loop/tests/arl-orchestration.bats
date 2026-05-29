#!/usr/bin/env bats
# Orchestration-layer tests: decision functions + real-git integration scenario.
# Run: bats tests/arl-orchestration.bats

setup() {
  HELPERS="${BATS_TEST_DIRNAME}/../scripts/arl-helpers.sh"
  # shellcheck source=/dev/null
  source "$HELPERS"
  WORK="$(mktemp -d)"
  cd "$WORK"
}
teardown() { cd /; rm -rf "$WORK"; }

_contract() { # _contract <dir> <NNN> <slug> <file...>
  local dir="$1" n="$2" slug="$3"; shift 3
  { echo "scope_files:"; for f in "$@"; do echo "  - $f"; done; } > "$dir/contract-$n-$slug.md"
}

# --- arl_approve_action (c/d contradiction fix) -------------------------

@test "approve_action: c is skip_to_rescore (NOT terminal)" {
  run arl_approve_action c
  [ "$status" -eq 0 ]; [ "$output" = "skip_to_rescore" ]
}
@test "approve_action: d is exit_loop (terminal)" {
  run arl_approve_action d
  [ "$output" = "exit_loop" ]
}
@test "approve_action: a/b map correctly, junk returns 2" {
  [ "$(arl_approve_action a)" = "approve_all" ]
  [ "$(arl_approve_action b)" = "select_ids" ]
  run arl_approve_action z; [ "$status" -eq 2 ]
}

# --- arl_check_termination ----------------------------------------------

@test "check_termination: weighted >= target -> DONE:target (float ok)" {
  run arl_check_termination 95.2 95 4 1 10 0
  [ "$output" = "DONE:target" ]
}
@test "check_termination: viable 0 -> plateau" {
  run arl_check_termination 80 95 0 1 10 0
  [ "$output" = "DONE:plateau" ]
}
@test "check_termination: iteration cap -> max_iter" {
  run arl_check_termination 80 95 3 10 10 0
  [ "$output" = "DONE:max_iter" ]
}
@test "check_termination: user exit beats everything" {
  run arl_check_termination 80 95 3 1 10 1
  [ "$output" = "DONE:user_stop" ]
}
@test "check_termination: otherwise CONTINUE" {
  run arl_check_termination 80 95 3 1 10 0
  [ "$output" = "CONTINUE" ]
}

# --- arl_activation_gate -------------------------------------------------

@test "activation_gate: not requested -> FALLBACK" {
  run arl_activation_gate 0 src 9 9
  [ "$output" = "FALLBACK" ]
}
@test "activation_gate: requested + open>=5 + approved>=3 -> MULTI_AGENT" {
  run arl_activation_gate 1 /nonexistent 5 3
  [ "$output" = "MULTI_AGENT" ]
}
@test "activation_gate: approved<3 -> FALLBACK" {
  run arl_activation_gate 1 /nonexistent 5 2
  [ "$output" = "FALLBACK" ]
}
@test "activation_gate: small repo AND open<5 -> FALLBACK" {
  mkdir small; : > small/f
  run arl_activation_gate 1 small 4 3
  [ "$output" = "FALLBACK" ]
}

# --- arl_dispatch_waves --------------------------------------------------

@test "dispatch_waves: serialize within conflict group, parallel across" {
  mkdir -p c
  _contract c 001 aa app/x.py
  _contract c 002 bb app/x.py        # conflicts with aa
  _contract c 003 cc lib/z.py        # disjoint
  run arl_dispatch_waves c 5
  [ "$status" -eq 0 ]
  # wave 1 must contain exactly one of {aa,bb} plus cc; the other of {aa,bb} in wave 2
  local w1="" w2=""
  for l in "${lines[@]}"; do
    case "$l" in "wave 1:"*) w1="$l";; "wave 2:"*) w2="$l";; esac
  done
  [ -n "$w1" ]; [ -n "$w2" ]
  [[ "$w1" == *cc* ]]
  # aa and bb never in the same wave
  [[ ! ( "$w1" == *aa* && "$w1" == *bb* ) ]]
}

@test "dispatch_waves: caps at n_workers per wave" {
  mkdir -p c
  _contract c 001 aa a.py
  _contract c 002 bb b.py
  _contract c 003 cc c.py            # all disjoint -> all parallel-eligible
  run arl_dispatch_waves c 2
  [ "$status" -eq 0 ]
  # n=2 -> wave1 has 2 slugs, wave2 has 1
  local w1count
  w1count=$(echo "$output" | awk '/^wave 1:/{print NF-2}')
  [ "$w1count" -eq 2 ]
  [[ "$output" == *"wave 2:"* ]]
}

# --- integration: parallel branches end-to-end (real git + bare remote) --

@test "integration: parallel disjoint contracts merge cleanly via helpers" {
  # real bare remote so fetch/switch/pull/merge/push actually run
  local ORIGIN="$WORK/origin.git"
  git init -q --bare "$ORIGIN"
  git clone -q "$ORIGIN" clone
  cd clone
  git config user.email a@b.c; git config user.name t
  echo base > base.txt; git add base.txt; git commit -q -m base
  git branch -M main; git push -q origin main

  mkdir -p .planning/quality/contracts
  _contract .planning/quality/contracts 001 aa a.py
  _contract .planning/quality/contracts 002 bb b.py
  _contract .planning/quality/contracts 003 cc c.py

  # all in one wave (disjoint), n=5
  run arl_dispatch_waves .planning/quality/contracts 5
  [ "$status" -eq 0 ]
  [[ "$output" == *"wave 1:"* ]]
  [[ "$output" != *"wave 2:"* ]]

  # PHASE 1 — parallel create from the SAME base, commit, push (subshells keep cwd)
  for slug in aa bb cc; do
    ( source "$HELPERS"
      arl_worktree_ensure "$slug" origin/main >/dev/null 2>&1
      echo "$slug" > "$slug.py"
      git add "$slug.py"
      git commit -q -m "quality: $slug"
      git push -q origin "quality/$slug" ) || false
  done

  # PHASE 2 — sequential merge: 1st fast-forwards, 2nd/3rd hit real-merge fallback
  for slug in aa bb cc; do
    arl_local_merge "$slug" >/dev/null 2>&1 || { echo "merge failed for $slug" >&2; false; }
  done

  # PHASE 3 — cleanup codex worktrees
  for slug in aa bb cc; do arl_worktree_cleanup "$slug" >/dev/null 2>&1; done

  # ASSERT — main carries all three worker files
  git switch -q main
  git pull -q --ff-only origin main
  [ -f a.py ] && [ -f b.py ] && [ -f c.py ]
  # ASSERT — no orphan quality-* worktrees remain
  run git worktree list
  [[ "$output" != *"quality-"* ]]
}
