#!/usr/bin/env python3
"""Test runner for state-write-guard.sh hook.

Script-style: invokes the hook via subprocess with JSON on stdin.
Mirrors hooks/test_pre_reviewer_write.py scaffold pattern.

Covers:
  - state.json Edit deny (rel + abs-prefix)
  - normal-path allow
  - AUTO_PILOT_ALLOW_STATE_WRITE=1 bypass allow
  - git am deny, git format-patch deny
  - git -C path am deny (intermediate-flag bypass blocked)
  - AUTO_PILOT_ALLOW_MAIN_MUTATE=1 env bypass allow
  - git log | grep am allow (no false-deny)
  - git commit allow (branch-lock's domain, not this guard)
  - malformed JSON fail-closed deny
  - non-dict tool_input fail-closed deny
  - separator/subshell/cmd-sub bypass deny, path-traversal deny
  - D4: shell-write to state.json (redirect/tee/cp/mv/dd) deny + benign allow
  - D5: tech-critic-lead reviewer role covered; unguarded role no-op
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).parent / "state-write-guard.sh")
_WORKER_ROLE = "worker"


def run_case(
    label: str,
    expect: str,
    payload_str: str,
    env_extra: dict[str, str] | None = None,
    role: str = _WORKER_ROLE,
) -> bool:
    env = os.environ.copy()
    env["AUTO_PILOT_SUBAGENT_ROLE"] = role
    # Clear bypass envs so they don't leak from the outer shell
    env.pop("AUTO_PILOT_ALLOW_STATE_WRITE", None)
    env.pop("AUTO_PILOT_ALLOW_MAIN_MUTATE", None)
    if env_extra:
        env.update(env_extra)

    result = subprocess.run(
        ["bash", HOOK],
        input=payload_str,
        capture_output=True,
        text=True,
        env=env,
    )

    if expect == "DENY":
        actual = "DENY" if result.returncode == 2 else "ALLOW"
    else:
        actual = "ALLOW" if result.returncode == 0 else "DENY"

    pass_fail = "PASS" if actual == expect else "FAIL"
    status_icon = "OK  " if pass_fail == "PASS" else "FAIL"
    print(f"[{status_icon}] {label:55s}  expect={expect:5s}  got={actual:5s}  rc={result.returncode}")
    if pass_fail == "FAIL":
        print(f"       payload: {payload_str!r}")
        print(f"       stderr:  {result.stderr.strip()!r}")
        print(f"       stdout:  {result.stdout.strip()!r}")
    return pass_fail == "PASS"


CASES: list[tuple[str, str, str]] = [
    # Case 1: Edit relative state.json path → DENY
    (
        "Edit .planning/auto-pilot/state.json (rel) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": ".planning/auto-pilot/state.json"},
        }),
    ),
    # Case 2: Edit absolute state.json path (any-abs-prefix) → DENY
    (
        "Edit /abs/proj/.planning/auto-pilot/state.json → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/abs/proj/.planning/auto-pilot/state.json"},
        }),
    ),
    # Case 3: Edit a normal source file → ALLOW
    (
        "Edit scripts/foo.py → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "scripts/foo.py"},
        }),
    ),
    # Case 4: Edit state.json + AUTO_PILOT_ALLOW_STATE_WRITE=1 → ALLOW
    (
        "Edit state.json + ALLOW_STATE_WRITE=1 env → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": ".planning/auto-pilot/state.json"},
        }),
    ),
    # Case 5: Bash git am patch → DENY
    (
        "Bash git am --3way patch.mbox → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git am --3way patch.mbox"},
        }),
    ),
    # Case 6: Bash git format-patch → DENY
    (
        "Bash git format-patch HEAD~1 → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git format-patch HEAD~1"},
        }),
    ),
    # Case 7: Bash git -C /repo am → DENY (intermediate-flag bypass blocked)
    (
        "Bash git -C /repo am x.mbox → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git -C /repo am x.mbox"},
        }),
    ),
    # Case 8: Bash git am + AUTO_PILOT_ALLOW_MAIN_MUTATE=1 env → ALLOW
    (
        "Bash git am + ALLOW_MAIN_MUTATE=1 env → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git am patch.mbox"},
        }),
    ),
    # Case 9: Bash pipeline containing 'am' as non-verb token → ALLOW (no FP)
    (
        "Bash git log | grep am (am as grep arg) → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git log --oneline | grep am"},
        }),
    ),
    # Case 10: Bash git commit → ALLOW (branch-lock's domain, not this guard)
    (
        "Bash git commit -m x → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'update'"},
        }),
    ),
    # Case 11: malformed JSON → DENY (fail-closed)
    (
        "malformed JSON → DENY (fail-closed)",
        "DENY",
        "not valid json {{",
    ),
    # Case 12: non-dict tool_input → DENY (fail-closed)
    (
        "non-dict tool_input {tool_input: string} → DENY (fail-closed)",
        "DENY",
        json.dumps({"tool_name": "Edit", "tool_input": "a string not a dict"}),
    ),
    # Case 13 (SEC5 class): command-string bypass prefix is NOT a self-grant → DENY
    (
        "Bash AUTO_PILOT_ALLOW_MAIN_MUTATE=1 cmd-prefix (not env) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "AUTO_PILOT_ALLOW_MAIN_MUTATE=1 git am patch.mbox"},
        }),
    ),
    # --- Hardening payloads: separator-bypass and path-traversal ---

    # P13: ;-adjacent separator hides git am
    (
        "Bash true;git am p.mbox (;-adjacent) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "true;git am p.mbox"},
        }),
    ),
    # P14: &&-adjacent separator hides git apply
    (
        "Bash true&&git apply p.patch (&&-adjacent) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "true&&git apply p.patch"},
        }),
    ),
    # P15: subshell wrapping hides git am
    (
        "Bash (git am p.mbox) subshell → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "(git am p.mbox)"},
        }),
    ),
    # P16: command-substitution eval-construct → fail-closed (DENY)
    (
        "Bash x=$(git apply p.patch) eval-construct → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "x=$(git apply p.patch)"},
        }),
    ),
    # P17: path-traversal ../ normalized before pattern match → DENY
    (
        "Edit /repo/.planning/auto-pilot/../auto-pilot/state.json path-traversal → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "/repo/.planning/auto-pilot/../auto-pilot/state.json"},
        }),
    ),
]

# Case 4 and case 8 need env overrides injected at runtime; wire them here.
_CASE_ENV_OVERRIDES: dict[int, dict[str, str]] = {
    3: {"AUTO_PILOT_ALLOW_STATE_WRITE": "1"},   # index 3 = case 4
    7: {"AUTO_PILOT_ALLOW_MAIN_MUTATE": "1"},   # index 7 = case 8
}


def _state(path: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": path}})


# D4 + D5 regression cases (label, expect, payload, env_extra, role).
# D4: a worker must not be able to clobber state.json via a shell write
#     (redirect / tee / cp / mv / dd). D5: tech-critic-lead is a reviewer role
#     and must be covered by the same guard.
EXTRA_CASES: list[tuple[str, str, str, dict[str, str] | None, str]] = [
    # D4: redirect overwrite → DENY
    (
        "D4 echo > state.json (redirect) → DENY",
        "DENY",
        _state("echo bad > .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: redirect append → DENY
    (
        "D4 echo >> state.json (append) → DENY",
        "DENY",
        _state("echo bad >> .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: attached redirect (no space) → DENY
    (
        "D4 echo >state.json (attached) → DENY",
        "DENY",
        _state("echo bad >.planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: absolute target → DENY
    (
        "D4 echo > /repo/.planning/auto-pilot/state.json → DENY",
        "DENY",
        _state("echo bad > /repo/.planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: ../ traversal in redirect target normalizes to state.json → DENY
    (
        "D4 redirect ../ traversal to state.json → DENY",
        "DENY",
        _state("echo bad > .planning/auto-pilot/../auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: tee → DENY
    (
        "D4 tee state.json → DENY",
        "DENY",
        _state("echo bad | tee .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: cp final-arg destination → DENY
    (
        "D4 cp x state.json → DENY",
        "DENY",
        _state("cp x .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: mv final-arg destination → DENY
    (
        "D4 mv x state.json → DENY",
        "DENY",
        _state("mv x .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: dd of= target → DENY
    (
        "D4 dd of=state.json → DENY",
        "DENY",
        _state("dd if=x of=.planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: benign redirect to another path → ALLOW (no false-deny)
    (
        "D4 echo > /tmp/other.txt → ALLOW",
        "ALLOW",
        _state("echo ok > /tmp/other.txt"),
        None,
        _WORKER_ROLE,
    ),
    # D4: a different state.json that is NOT the loop file → ALLOW
    (
        "D4 echo > config/state.json (not loop path) → ALLOW",
        "ALLOW",
        _state("echo ok > config/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # D4: shell-write bypass honors ALLOW_STATE_WRITE=1 → ALLOW
    (
        "D4 redirect to state.json + ALLOW_STATE_WRITE=1 → ALLOW",
        "ALLOW",
        _state("echo ok > .planning/auto-pilot/state.json"),
        {"AUTO_PILOT_ALLOW_STATE_WRITE": "1"},
        _WORKER_ROLE,
    ),
    # D4: shell-write to state.json NOT bypassed by ALLOW_MAIN_MUTATE (wrong invariant) → DENY
    (
        "D4 redirect to state.json + ALLOW_MAIN_MUTATE=1 (wrong bypass) → DENY",
        "DENY",
        _state("echo bad > .planning/auto-pilot/state.json"),
        {"AUTO_PILOT_ALLOW_MAIN_MUTATE": "1"},
        _WORKER_ROLE,
    ),
    # D5: tech-critic-lead Edit to state.json → DENY (role now covered)
    (
        "D5 tech-critic-lead Edit state.json → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": ".planning/auto-pilot/state.json"},
        }),
        None,
        "tech-critic-lead",
    ),
    # D5: tech-critic-lead Bash shell-write to state.json → DENY
    (
        "D5 tech-critic-lead redirect to state.json → DENY",
        "DENY",
        _state("echo bad > .planning/auto-pilot/state.json"),
        None,
        "tech-critic-lead",
    ),
    # D5: an unguarded role stays a no-op → ALLOW
    (
        "D5 pm-orchestrator (unguarded role) Edit state.json → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": ".planning/auto-pilot/state.json"},
        }),
        None,
        "pm-orchestrator",
    ),
    # ── FIX 1: in-place / destructive writer bypass cases ──────────────────────
    # sed -i edits state.json in-place → DENY
    (
        "FIX1 sed -i .planning/auto-pilot/state.json → DENY",
        "DENY",
        _state("sed -i s/a/b/ .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # perl -i in-place → DENY
    (
        "FIX1 perl -i state.json → DENY",
        "DENY",
        _state("perl -i -e 's/a/b/g' .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # perl -pi in-place → DENY
    (
        "FIX1 perl -pi state.json → DENY",
        "DENY",
        _state("perl -pi -e 's/a/b/g' .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # install overwrites destination → DENY
    (
        "FIX1 install x state.json → DENY",
        "DENY",
        _state("install x .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # ln -sf symlink replaces state.json → DENY
    (
        "FIX1 ln -sf /tmp/x state.json → DENY",
        "DENY",
        _state("ln -sf /tmp/x .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # rm deletes state.json (defeats lock invariant) → DENY
    (
        "FIX1 rm .planning/auto-pilot/state.json → DENY",
        "DENY",
        _state("rm .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # ed editor targeting state.json → DENY
    (
        "FIX1 ed .planning/auto-pilot/state.json → DENY",
        "DENY",
        _state("ed .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # ex editor targeting state.json → DENY
    (
        "FIX1 ex .planning/auto-pilot/state.json → DENY",
        "DENY",
        _state("ex .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # awk with embedded redirect inside program string → DENY
    (
        "FIX1 awk embedded redirect to state.json → DENY",
        "DENY",
        _state('awk \'BEGIN{print > ".planning/auto-pilot/state.json"}\' input.txt'),
        None,
        _WORKER_ROLE,
    ),
    # positive: sed -i on a NON-state file must still be allowed
    (
        "FIX1 sed -i scripts/foo.py (not state) → ALLOW",
        "ALLOW",
        _state("sed -i s/a/b/ scripts/foo.py"),
        None,
        _WORKER_ROLE,
    ),
    # positive: cat state.json (read) must still be allowed
    (
        "FIX1 cat state.json (read-only) → ALLOW",
        "ALLOW",
        _state("cat .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # positive: jq . state.json (read) must still be allowed
    (
        "FIX1 jq . state.json (read-only) → ALLOW",
        "ALLOW",
        _state("jq . .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # ── FIX 2: fd-numbered redirect operators ──────────────────────────────────
    # echo 1> state.json (fd-prefixed overwrite) → DENY
    (
        "FIX2 echo 1> state.json → DENY",
        "DENY",
        _state("echo bad 1> .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
    # echo 1>> state.json (fd-prefixed append) → DENY
    (
        "FIX2 echo 1>> state.json → DENY",
        "DENY",
        _state("echo bad 1>> .planning/auto-pilot/state.json"),
        None,
        _WORKER_ROLE,
    ),
]


def main() -> None:
    results: list[bool] = []
    for idx, case in enumerate(CASES):
        label, expect, payload = case
        env_extra = _CASE_ENV_OVERRIDES.get(idx)
        results.append(run_case(label, expect, payload, env_extra))

    for label, expect, payload, env_extra, role in EXTRA_CASES:
        results.append(run_case(label, expect, payload, env_extra, role))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
