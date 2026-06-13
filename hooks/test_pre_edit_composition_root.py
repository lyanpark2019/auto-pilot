#!/usr/bin/env python3
"""Test runner for pre-edit-composition-root.sh hook.

Script-style: invokes the hook via subprocess to mimic the harness handing
JSON via stdin.  Matches the pattern of hooks/test_pre_edit_human_only.py.

Covers:
  - Malformed / truncated JSON → DENY (exit 2, fail-closed) [FIX 3]
  - Valid JSON with no file_path key → ALLOW (exit 0, not a parse failure)
  - Existing populated __init__.py → DENY (normal deny rule, regression guard)
  - New / empty __init__.py → ALLOW (normal allow path)
  - Non-root file → ALLOW (normal allow path)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "pre-edit-composition-root.sh")


def run_case(
    label: str,
    expect: str,
    payload_str: str,
    env_extra: dict[str, str] | None = None,
) -> bool:
    env = os.environ.copy()
    env.pop("AUTO_PILOT_FORCE_COMPOSITION_ROOT", None)
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


def main() -> None:
    results: list[bool] = []

    # FIX 3: blocking guard must fail-closed on malformed JSON, not skip.
    results.append(run_case(
        "Malformed JSON (truncated) → DENY",
        "DENY",
        "TRUNCATED{{{garbage",
    ))
    results.append(run_case(
        "Empty string stdin → DENY",
        "DENY",
        "",
    ))
    results.append(run_case(
        "Partial JSON (unclosed brace) → DENY",
        "DENY",
        '{"tool_input":',
    ))

    # Valid JSON but no file_path key → ALLOW (not a parse failure).
    results.append(run_case(
        "Valid JSON, no file_path key → ALLOW",
        "ALLOW",
        json.dumps({"tool_input": {"command": "ls"}}),
    ))
    results.append(run_case(
        "Valid JSON, empty tool_input → ALLOW",
        "ALLOW",
        json.dumps({"tool_input": {}}),
    ))

    with tempfile.TemporaryDirectory() as tmpdir:
        # Normal deny: existing populated __init__.py → DENY.
        pkg_dir = os.path.join(tmpdir, "mypkg")
        os.makedirs(pkg_dir)
        populated_init = os.path.join(pkg_dir, "__init__.py")
        Path(populated_init).write_text("from .x import Y\nfrom .z import W\n")

        results.append(run_case(
            "Existing populated __init__.py → DENY",
            "DENY",
            json.dumps({"tool_input": {"file_path": populated_init}}),
        ))

        # Bypass switch re-allows the deny.
        results.append(run_case(
            "Populated __init__.py + FORCE bypass → ALLOW",
            "ALLOW",
            json.dumps({"tool_input": {"file_path": populated_init}}),
            env_extra={"AUTO_PILOT_FORCE_COMPOSITION_ROOT": "1"},
        ))

        # New (not-yet-created) __init__.py → ALLOW.
        new_init = os.path.join(pkg_dir, "new_pkg", "__init__.py")
        results.append(run_case(
            "Non-existent __init__.py → ALLOW",
            "ALLOW",
            json.dumps({"tool_input": {"file_path": new_init}}),
        ))

        # Empty __init__.py → ALLOW.
        empty_init = os.path.join(pkg_dir, "empty_init.py")
        Path(empty_init).write_text("")
        results.append(run_case(
            "Empty __init__.py → ALLOW",
            "ALLOW",
            json.dumps({"tool_input": {"file_path": empty_init}}),
        ))

        # Non-root file → ALLOW.
        normal_file = os.path.join(tmpdir, "normal.py")
        Path(normal_file).write_text("x = 1\n")
        results.append(run_case(
            "Non-root Python file → ALLOW",
            "ALLOW",
            json.dumps({"tool_input": {"file_path": normal_file}}),
        ))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
