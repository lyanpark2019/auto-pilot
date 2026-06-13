#!/usr/bin/env python3
"""Test runner for pre-bash-guard.sh hook.

Script-style: invokes the hook via subprocess to mimic the harness handing
JSON via stdin.  Matches the pattern of hooks/test_pre_edit_human_only.py.

Covers:
  - Malformed / truncated JSON → DENY (exit 2, fail-closed) [FIX 2]
  - Valid JSON with no command key → ALLOW (exit 0, not a parse failure)
  - claude doctor command → DENY (normal deny rule, regression guard)
  - Plain allowed command (git status) → ALLOW (normal allow path)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).parent / "pre-bash-guard.sh")


def run_case(
    label: str,
    expect: str,
    payload_str: str,
    env_extra: dict[str, str] | None = None,
) -> bool:
    env = os.environ.copy()
    # Ensure bypass switch is off for all deny/allow tests (unless overridden).
    env.pop("AUTO_PILOT_BASH_BYPASS", None)
    if env_extra:
        env.update(env_extra)

    result = subprocess.run(
        ["bash", HOOK],
        input=payload_str,
        capture_output=True,
        text=True,
        env=env,
    )

    actual = "DENY" if result.returncode == 2 else "ALLOW"
    pass_fail = "PASS" if actual == expect else "FAIL"
    icon = "OK  " if pass_fail == "PASS" else "FAIL"
    print(
        f"[{icon}] {label:55s}  expect={expect:5s}  got={actual:5s}  rc={result.returncode}"
    )
    if pass_fail == "FAIL":
        print(f"       payload: {payload_str!r}")
        print(f"       stderr:  {result.stderr.strip()!r}")
        print(f"       stdout:  {result.stdout.strip()!r}")
    return pass_fail == "PASS"


CASES: list[tuple[str, str, str]] = [
    # FIX 2: blocking guard must fail-closed on malformed JSON, not skip.
    (
        "Malformed JSON (truncated) → DENY",
        "DENY",
        "TRUNCATED{{{garbage",
    ),
    (
        "Empty string stdin → DENY",
        "DENY",
        "",
    ),
    (
        "Partial JSON (unclosed brace) → DENY",
        "DENY",
        '{"tool_input":',
    ),
    # Valid JSON but no command key → ALLOW (not a parse failure).
    (
        "Valid JSON, no command key → ALLOW",
        "ALLOW",
        json.dumps({"tool_input": {"other": "val"}}),
    ),
    (
        "Valid JSON, empty tool_input → ALLOW",
        "ALLOW",
        json.dumps({"tool_input": {}}),
    ),
    # Normal deny rule regression: claude doctor still blocked.
    (
        "claude doctor command → DENY",
        "DENY",
        json.dumps({"tool_input": {"command": "claude doctor"}}),
    ),
    # Normal allow regression: plain read command passes.
    (
        "git status command → ALLOW",
        "ALLOW",
        json.dumps({"tool_input": {"command": "git status"}}),
    ),
    (
        "python3 -m pytest → ALLOW",
        "ALLOW",
        json.dumps({"tool_input": {"command": "python3 -m pytest -q"}}),
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
