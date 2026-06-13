#!/usr/bin/env python3
"""Test runner for subagent-deliverable-check.sh hook.

Script-style: invokes the hook via subprocess, mirroring the structure of
hooks/test_pre_edit_human_only.py.

Covers:
  - Existing: hallucinated-file path check still warns (regression pin).
  - NEW check (a): DONE + NO verify SHA → warns about missing verify evidence.
    RED-FIRST: this test is written before the hook is edited; it MUST FAIL
    initially (current hook emits no such warning).
  - NEW check (a) negative: DONE + valid SHA-256 line present → no warn.
  - NEW check (a) negative: BLOCKED status without SHA → no warn (only DONE
    triggers the check).
  - NEW check (a) negative: PARTIAL status without SHA → no warn.
  - NEW check (b): AUTO_PILOT_SCOPE_FILES includes tests/ path + DONE report
    changing no test file → warns.
  - NEW check (b) inert: same payload but AUTO_PILOT_SCOPE_FILES unset → no warn.
  - All cases: hook always exits 0 (advisory, never blocking).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).parent / "subagent-deliverable-check.sh")
PLUGIN_ROOT = str(Path(__file__).parent.parent)

WARN_VERIFY = "[subagent-deliverable-check] WARNING: report marked DONE but carries no verify-log SHA-256"
WARN_TESTS = "[subagent-deliverable-check] WARNING: contract scope includes test files but the DONE report changed none"
WARN_HALLUCINATE = "[subagent-deliverable-check] WARNING: subagent claimed to write"

# A valid SHA-256 hex string (64 chars)
VALID_SHA = "a" * 64

# A DONE report with no verify-SHA evidence
DONE_REPORT_NO_SHA = """\
## Worker 1 Report — Contract 1

**Status:** DONE
**Files changed:** scripts/foo.py
**Lines added/removed:** +10 / -2

**Summary:**
Added the foo function.

**Verify log:** .planning/auto-pilot/verify-logs/phase-1-worker-1.log
"""

# A DONE report with a valid Verify log SHA-256 line
DONE_REPORT_WITH_SHA = f"""\
## Worker 1 Report — Contract 1

**Status:** DONE
**Files changed:** scripts/foo.py
**Lines added/removed:** +10 / -2

**Summary:**
Added the foo function.

**Verify log:** .planning/auto-pilot/verify-logs/phase-1-worker-1.log
**Verify log SHA-256:** {VALID_SHA}  .planning/auto-pilot/verify-logs/phase-1-worker-1.log
"""

# A BLOCKED report with no SHA (should NOT trigger check-a)
BLOCKED_REPORT_NO_SHA = """\
## Worker 1 Report — Contract 1

**Status:** BLOCKED
**Files changed:** (none)

**Summary:**
Cannot proceed due to missing dependency.
"""

# A PARTIAL report with no SHA (should NOT trigger check-a)
PARTIAL_REPORT_NO_SHA = """\
## Worker 1 Report — Contract 1

**Status:** PARTIAL
**Files changed:** scripts/foo.py

**Summary:**
Half-done.
"""

# A DONE report that changes no test files (for check-b)
DONE_REPORT_NO_TEST_CHANGES = """\
## Worker 1 Report — Contract 1

**Status:** DONE
**Files changed:** scripts/foo.py, scripts/bar.py
**Lines added/removed:** +20 / -5

**Verify log SHA-256:** {sha}  .planning/auto-pilot/verify-logs/phase-1-worker-1.log
""".format(sha=VALID_SHA)


def make_payload(output_text: str) -> str:
    """Build the SubagentStop JSON payload the hook expects."""
    return json.dumps({
        "stop_reason": "end_turn",
        "result": {"output": output_text},
    })


def run_hook(
    label: str,
    output_text: str,
    expect_exit: int,
    expect_warn_verify: bool,
    expect_warn_tests: bool,
    expect_warn_hallucinate: bool = False,
    env_extra: dict[str, str] | None = None,
) -> bool:
    """Run the hook with given output_text, assert exit code and warning presence.

    The hook pipes python3 stderr through '2>&1 || true', so all warnings land
    in the hook's stdout.  We search the combined output (stdout + stderr) for
    warning strings so the test is robust to future redirection changes.
    """
    env = os.environ.copy()
    # Always clear scope-files unless test wants it
    env.pop("AUTO_PILOT_SCOPE_FILES", None)
    if env_extra:
        env.update(env_extra)

    payload = make_payload(output_text)
    result = subprocess.run(
        ["bash", HOOK],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=PLUGIN_ROOT,
    )
    # Hook uses `python3 ... 2>&1 || true` so warnings appear in stdout.
    combined = result.stdout + result.stderr
    exit_ok = result.returncode == expect_exit
    verify_warn_ok = (WARN_VERIFY in combined) == expect_warn_verify
    tests_warn_ok = (WARN_TESTS in combined) == expect_warn_tests
    hallucinate_warn_ok = (WARN_HALLUCINATE in combined) == expect_warn_hallucinate
    ok = exit_ok and verify_warn_ok and tests_warn_ok and hallucinate_warn_ok
    icon = "OK  " if ok else "FAIL"
    print(
        f"[{icon}] {label:70s}"
        f"  exit={result.returncode}(want={expect_exit})"
        f"  verify_warn={'Y' if WARN_VERIFY in combined else 'N'}(want={'Y' if expect_warn_verify else 'N'})"
        f"  tests_warn={'Y' if WARN_TESTS in combined else 'N'}(want={'Y' if expect_warn_tests else 'N'})"
    )
    if not ok:
        print(f"       combined: {combined.strip()!r}")
        print(f"       rc: {result.returncode}")
    return ok


def run_hook_bytes(
    label: str,
    stdin_bytes: bytes,
    expect_exit: int,
    env_extra: dict[str, str] | None = None,
) -> bool:
    """Run the hook with raw bytes on stdin (for malformed-JSON paths)."""
    env = os.environ.copy()
    env.pop("AUTO_PILOT_SCOPE_FILES", None)
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["bash", HOOK],
        input=stdin_bytes,
        capture_output=True,
        env=env,
        cwd=PLUGIN_ROOT,
    )
    ok = result.returncode == expect_exit
    icon = "OK  " if ok else "FAIL"
    combined = result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace")
    print(
        f"[{icon}] {label:70s}"
        f"  exit={result.returncode}(want={expect_exit})"
    )
    if not ok:
        print(f"       combined: {combined.strip()!r}")
    return ok


def main() -> None:
    results: list[bool] = []

    # --- Regression: existing hallucinated-file path check still fires ---
    hallucinated_text = "wrote /tmp/does_not_exist_xyz_abc_123/file.py and saved results."
    results.append(run_hook(
        "existing hallucinated-path → warns about missing file",
        output_text=hallucinated_text,
        expect_exit=0,
        expect_warn_verify=False,
        expect_warn_tests=False,
        expect_warn_hallucinate=True,
    ))

    # --- Check (a): DONE + NO verify SHA → warns ---
    # RED-FIRST case: this MUST FAIL before the hook is edited.
    results.append(run_hook(
        "DONE + no verify SHA → warns (check-a) [RED-FIRST]",
        output_text=DONE_REPORT_NO_SHA,
        expect_exit=0,
        expect_warn_verify=True,   # expect warning — hook doesn't emit it yet
        expect_warn_tests=False,
    ))

    # --- Check (a) negative: DONE + valid SHA line → no verify warn ---
    results.append(run_hook(
        "DONE + valid SHA-256 line → no verify-warn (check-a negative)",
        output_text=DONE_REPORT_WITH_SHA,
        expect_exit=0,
        expect_warn_verify=False,
        expect_warn_tests=False,
    ))

    # --- Check (a) negative: BLOCKED + no SHA → no verify warn ---
    results.append(run_hook(
        "BLOCKED + no SHA → no verify-warn (only DONE triggers)",
        output_text=BLOCKED_REPORT_NO_SHA,
        expect_exit=0,
        expect_warn_verify=False,
        expect_warn_tests=False,
    ))

    # --- Check (a) negative: PARTIAL + no SHA → no verify warn ---
    results.append(run_hook(
        "PARTIAL + no SHA → no verify-warn (only DONE triggers)",
        output_text=PARTIAL_REPORT_NO_SHA,
        expect_exit=0,
        expect_warn_verify=False,
        expect_warn_tests=False,
    ))

    # --- Check (b): scope includes tests/ path + DONE + no test in diff → warns ---
    scope_with_tests = "scripts/foo.py tests/test_foo.py"
    results.append(run_hook(
        "check-b: scope has tests/ + DONE + no test in report → warns",
        output_text=DONE_REPORT_NO_TEST_CHANGES,
        expect_exit=0,
        expect_warn_verify=False,   # SHA is present, so no verify-warn
        expect_warn_tests=True,
        env_extra={"AUTO_PILOT_SCOPE_FILES": scope_with_tests},
    ))

    # --- Check (b) inert: same payload but scope-files unset → no tests warn ---
    results.append(run_hook(
        "check-b inert: AUTO_PILOT_SCOPE_FILES unset → no tests-warn",
        output_text=DONE_REPORT_NO_TEST_CHANGES,
        expect_exit=0,
        expect_warn_verify=False,
        expect_warn_tests=False,
        # env_extra not set → AUTO_PILOT_SCOPE_FILES absent
    ))

    # --- Check (b) negative: scope has tests/ + DONE + diff includes test file → no tests warn ---
    done_with_test_change = DONE_REPORT_NO_TEST_CHANGES.replace(
        "scripts/foo.py, scripts/bar.py",
        "scripts/foo.py, tests/test_foo.py",
    )
    results.append(run_hook(
        "check-b negative: scope has tests/ + DONE + test file present → no tests-warn",
        output_text=done_with_test_change,
        expect_exit=0,
        expect_warn_verify=False,
        expect_warn_tests=False,
        env_extra={"AUTO_PILOT_SCOPE_FILES": scope_with_tests},
    ))

    # --- P2-b regression: stray 64-hex in prose must NOT suppress verify warn ---
    # This was a false-negative: the old broad regex matched any bare 64-hex token.
    # RED-FIRST: must FAIL against the old hook (broad regex), PASS after the fix.
    stray_sha = "deadbeef" + "0" * 56  # 64 hex chars, valid format but unlabeled
    report_stray_sha = (
        "## Worker 1 Report — Contract 1\n\n"
        "**Status:** DONE\n"
        "**Files changed:** scripts/foo.py\n"
        "**Lines added/removed:** +10 / -2\n\n"
        "**Summary:**\n"
        f"Did some work. the artifact sha256 is {stray_sha}\n\n"
        "**Verify log:** .planning/auto-pilot/verify-logs/phase-1-worker-1.log\n"
    )
    results.append(run_hook(
        "P2-b reg1: DONE + stray 64-hex in prose (unlabeled) → verify warn fires",
        output_text=report_stray_sha,
        expect_exit=0,
        expect_warn_verify=True,   # stray sha must NOT suppress check-a
        expect_warn_tests=False,
    ))

    # --- P2-b regression: test path only in prose must NOT suppress tests warn ---
    # The old broad regex searched all text; prose like "I considered tests/test_x.py"
    # suppressed the check.  After the fix, only Files-changed and diff +++ lines count.
    # RED-FIRST: must FAIL against the old hook, PASS after the fix.
    report_test_prose_only = (
        "## Worker 1 Report — Contract 1\n\n"
        "**Status:** DONE\n"
        "**Files changed:** scripts/foo.py\n"
        "**Lines added/removed:** +10 / -2\n\n"
        "**Summary:**\n"
        "I considered tests/test_x.py but decided not to touch it.\n\n"
        f"**Verify log SHA-256:** {VALID_SHA}  path/to/log\n"
    )
    results.append(run_hook(
        "P2-b reg2: DONE + test only in prose → tests warn fires",
        output_text=report_test_prose_only,
        expect_exit=0,
        expect_warn_verify=False,
        expect_warn_tests=True,   # prose mention must NOT suppress check-b
        env_extra={"AUTO_PILOT_SCOPE_FILES": "scripts/foo.py tests/test_x.py"},
    ))

    # --- hook is always advisory (exit 0) even for empty output ---
    results.append(run_hook(
        "empty output -> exits 0",
        output_text="",  # empty output; hook exits early (not-a-string / empty check)
        expect_exit=0,
        expect_warn_verify=False,
        expect_warn_tests=False,
    ))

    # --- malformed JSON bytes → except branch → exits 0 (pins the except clause) ---
    # Feeds raw non-JSON bytes; the hook's `except Exception: sys.exit(0)` must fire.
    results.append(run_hook_bytes(
        "malformed JSON bytes → exits 0 (pins except: sys.exit(0) branch)",
        stdin_bytes=b"not json",
        expect_exit=0,
    ))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
