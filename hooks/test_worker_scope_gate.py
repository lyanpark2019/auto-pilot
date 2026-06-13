#!/usr/bin/env python3
"""Script-style test runner for worker-scope-gate.sh hook.

Mirrors hooks/test_guard_destructive.py style: subprocess calls with JSON stdin,
assert exit code expectations.

Test contract:
- AUTO_PILOT_SUBAGENT_ROLE=worker + scope set + edit outside scope → exit 2 (BLOCKED)
- AUTO_PILOT_SUBAGENT_ROLE=worker + scope set + edit inside scope → exit 0 (allow)
- AUTO_PILOT_SUBAGENT_ROLE unset → exit 0 (no-op)
- malformed JSON + worker role → exit 2 (fail-closed)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).parent / "worker-scope-gate.sh")


def run_case(
    label: str,
    expect_code: int,
    file_path: str | None,
    role: str | None,
    scope_files: str | None,
    malformed: bool = False,
) -> bool:
    if malformed:
        payload_bytes = b"not valid json {"
    elif file_path is not None:
        payload = {"tool_name": "Edit", "tool_input": {"file_path": file_path}}
        payload_bytes = json.dumps(payload).encode()
    else:
        payload_bytes = json.dumps({}).encode()

    env = os.environ.copy()
    if role is not None:
        env["AUTO_PILOT_SUBAGENT_ROLE"] = role
    else:
        env.pop("AUTO_PILOT_SUBAGENT_ROLE", None)

    if scope_files is not None:
        env["AUTO_PILOT_SCOPE_FILES"] = scope_files
    else:
        env.pop("AUTO_PILOT_SCOPE_FILES", None)

    result = subprocess.run(
        ["bash", HOOK],
        input=payload_bytes,
        capture_output=True,
        env=env,
    )

    actual = result.returncode
    pass_fail = "PASS" if actual == expect_code else "FAIL"
    status_icon = "OK  " if pass_fail == "PASS" else "FAIL"
    print(f"[{status_icon}] {label:50s}  expect={expect_code}  got={actual}")
    if pass_fail == "FAIL":
        print(f"       stdout: {result.stdout!r}")
        print(f"       stderr: {result.stderr!r}")
    return pass_fail == "PASS"


CASES = [
    # worker role + scope set + edit outside scope → BLOCKED (exit 2)
    (
        "worker role, out-of-scope edit → exit 2",
        2,
        "scripts/c.py",
        "worker",
        "scripts/a.py\nscripts/b.py",
        False,
    ),
    # worker role + scope set + edit inside scope → allow (exit 0)
    (
        "worker role, in-scope edit → exit 0",
        0,
        "scripts/a.py",
        "worker",
        "scripts/a.py\nscripts/b.py",
        False,
    ),
    # role unset → no-op (exit 0)
    (
        "role unset → exit 0 (no-op)",
        0,
        "scripts/c.py",
        None,
        "scripts/a.py\nscripts/b.py",
        False,
    ),
    # malformed JSON + worker role → fail-closed (exit 2)
    (
        "malformed JSON + worker role → exit 2 (fail-closed)",
        2,
        None,
        "worker",
        "scripts/a.py\nscripts/b.py",
        True,
    ),
    # space-separated scope, in-scope → exit 0
    (
        "space-separated scope, in-scope edit → exit 0",
        0,
        "scripts/b.py",
        "worker",
        "scripts/a.py scripts/b.py",
        False,
    ),
    # scope unset (worker role but no AUTO_PILOT_SCOPE_FILES) → no-op (exit 0)
    (
        "worker role, no scope set → exit 0 (no-op)",
        0,
        "scripts/c.py",
        "worker",
        None,
        False,
    ),
    # Whitespace-only file_path: not empty so [ -z "$file_path" ] is false → goes to scope
    # check; "   " is not in the scope list → BLOCKED (exit 2).
    (
        "worker role, whitespace-only file_path → exit 2 (not in scope)",
        2,
        "   ",
        "worker",
        "scripts/a.py\nscripts/b.py",
        False,
    ),
    # Whitespace-only scope_files: tr ' ' '\n' + strip leaves empty allowed list.
    # Any real file_path is out-of-scope → BLOCKED (exit 2).
    (
        "worker role, whitespace-only scope → exit 2 (empty allowlist)",
        2,
        "scripts/a.py",
        "worker",
        "   \n   ",
        False,
    ),
    # Tab-only file_path behaves the same as whitespace-only: not in scope → BLOCKED.
    (
        "worker role, tab-only file_path → exit 2 (not in scope)",
        2,
        "\t",
        "worker",
        "scripts/a.py\nscripts/b.py",
        False,
    ),
]


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
