#!/usr/bin/env python3
"""Test runner for state-write-guard.sh hook.

Script-style: invokes the hook via subprocess with JSON on stdin.
Mirrors hooks/test_pre_reviewer_write.py scaffold pattern.

12 cases covering:
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
) -> bool:
    env = os.environ.copy()
    env["AUTO_PILOT_SUBAGENT_ROLE"] = _WORKER_ROLE
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


def main() -> None:
    results: list[bool] = []
    for idx, case in enumerate(CASES):
        label, expect, payload = case
        env_extra = _CASE_ENV_OVERRIDES.get(idx)
        results.append(run_case(label, expect, payload, env_extra))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
