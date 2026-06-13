#!/usr/bin/env python3
"""Test runner for pre-edit-human-only.sh hook.

Script-style: invokes the hook via subprocess, mirroring the structure of
hooks/test_branch_lock.py.

Covers:
  - Unparseable stdin → ALLOW (fail-open) + advisory on stderr
  - Normal allowed edit (valid payload, non-protected path) → ALLOW + NO advisory
  - Tier-2 protected path edit (schemas/) → DENY
  - AUTO_PILOT_ALLOW_CORE_EDIT=1 bypass for tier-2 path → ALLOW
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "pre-edit-human-only.sh")
ADVISORY_TAG = "[hook:pre-edit-human-only] fail-open"

# The plugin root is one level up from hooks/
PLUGIN_ROOT = str(Path(__file__).parent.parent)


def run_raw(
    label: str,
    raw_stdin: str,
    expect_allow: bool,
    expect_advisory: bool,
    env_extra: dict[str, str] | None = None,
) -> bool:
    """Feed raw stdin and check the allow decision + advisory presence."""
    env = os.environ.copy()
    env.pop("AUTO_PILOT_ALLOW_CORE_EDIT", None)
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["bash", HOOK],
        input=raw_stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=PLUGIN_ROOT,
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    is_allow = result.returncode == 0 and '"permissionDecision":"deny"' not in stdout
    advisory_present = ADVISORY_TAG in stderr
    ok = (is_allow == expect_allow) and (advisory_present == expect_advisory)
    icon = "OK  " if ok else "FAIL"
    print(
        f"[{icon}] {label:55s}"
        f"  allow={'Y' if is_allow else 'N'}(want={'Y' if expect_allow else 'N'})"
        f"  advisory={'Y' if advisory_present else 'N'}(want={'Y' if expect_advisory else 'N'})"
    )
    if not ok:
        print(f"       stdout: {stdout!r}")
        print(f"       stderr: {stderr!r}")
        print(f"       rc:     {result.returncode}")
    return ok


def run_case(
    label: str,
    file_path: str,
    expect: str,
    env_extra: dict[str, str] | None = None,
) -> bool:
    """Feed a well-formed Edit payload and check allow/deny decision."""
    env = os.environ.copy()
    env.pop("AUTO_PILOT_ALLOW_CORE_EDIT", None)
    if env_extra:
        env.update(env_extra)
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": file_path}})
    result = subprocess.run(
        ["bash", HOOK],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=PLUGIN_ROOT,
    )
    stdout = result.stdout.strip()
    actual = "DENY" if '"permissionDecision":"deny"' in stdout else "ALLOW"
    ok = actual == expect and result.returncode == 0
    icon = "OK  " if ok else "FAIL"
    print(f"[{icon}] {label:55s}  expect={expect:5s}  got={actual:5s}")
    if not ok:
        print(f"       stdout: {stdout!r}")
        print(f"       stderr: {result.stderr.strip()!r}")
    return ok


def main() -> None:
    results: list[bool] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        # A non-protected target file for legit-allow tests
        safe_file = os.path.join(tmpdir, "safe.py")
        Path(safe_file).write_text("x = 1\n")

        # 1. Unparseable stdin → fail-open ALLOW + advisory on stderr
        results.append(run_raw(
            "unparseable stdin → ALLOW + advisory",
            raw_stdin="not valid json {{{",
            expect_allow=True,
            expect_advisory=True,
        ))

        # 2. Empty stdin → fail-open ALLOW + advisory on stderr
        results.append(run_raw(
            "empty stdin → ALLOW + advisory",
            raw_stdin="",
            expect_allow=True,
            expect_advisory=True,
        ))

        # 3. Normal allowed edit (safe path, valid payload) → ALLOW + NO advisory
        results.append(run_raw(
            "normal allowed edit → ALLOW + NO advisory",
            raw_stdin=json.dumps({
                "tool_name": "Edit",
                "tool_input": {"file_path": safe_file},
            }),
            expect_allow=True,
            expect_advisory=False,
        ))

        # 4. Tier-2 protected path (schemas/) → DENY
        schemas_file = os.path.join(PLUGIN_ROOT, "schemas", "contract.schema.json")
        results.append(run_case(
            "schemas/ tier-2 → DENY",
            file_path=schemas_file,
            expect="DENY",
        ))

        # 5. Tier-2 with bypass env → ALLOW
        results.append(run_case(
            "schemas/ tier-2 + AUTO_PILOT_ALLOW_CORE_EDIT=1 → ALLOW",
            file_path=schemas_file,
            expect="ALLOW",
            env_extra={"AUTO_PILOT_ALLOW_CORE_EDIT": "1"},
        ))

        # 6. Non-Bash tool payload with no file_path (valid JSON, missing key)
        #    → ALLOW + NO advisory (legit non-edit invocation, not a parse failure)
        results.append(run_raw(
            "valid JSON, no file_path key → ALLOW + NO advisory",
            raw_stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
            expect_allow=True,
            expect_advisory=False,
        ))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
