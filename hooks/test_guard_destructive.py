#!/usr/bin/env python3
"""Test runner for guard-destructive.py hook.

Each test case is invoked via subprocess to mimic the harness handing
JSON via stdin. Test payloads are constructed in Python (not via shell
echo) so the bash invocation of THIS runner doesn't itself contain
destructive patterns that the hook would block.

TMPDIR isolation: every subprocess call overrides TMPDIR to an isolated
temp dir so live approval markers on the dev machine cannot bleed in and
flip expected DENY → allow. Without this, batch markers accumulated in the
real TMPDIR (e.g. from prior sessions) would silently override the guard.
"""
import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "guard-destructive.py")

# Each test: (label, expect, command_string)
# expect: "ALLOW" (silent exit 0) or "DENY" (JSON deny output)
# Patterns are constructed via base64 / chr() to avoid having destructive
# substrings appear in this file as plain text — even though the hook
# only scans Bash tool calls, not file contents, keeping the strings
# out of plaintext makes future code review of the test file safe.

def b(s: str) -> str:
    return base64.b64decode(s).decode()

CASES = [
    # A. Commit with destructive patterns inside heredoc body — should ALLOW after scrub
    ("A heredoc commit body",
     "ALLOW",
     'git commit -m "$(cat <<\'EOF\'\ndocs about ' + b("cm0gLXJm") + ' and DROP TABLE\nand DELETE FROM users\nand git push --force docs\nEOF\n)"'),

    # B. Commit -m "..." mentioning destructive — should ALLOW after scrub
    ("B dash-m commit string",
     "ALLOW",
     'git commit -m "docs: ban ' + b("cm0gLXJm") + ' going forward"'),

    # C. Real destructive command — should still DENY
    ("C real recursive delete",
     "DENY",
     b("cm0gLXJm") + " /tmp/foo"),

    # D. mcpl with bare SQL DELETE — should still DENY
    ("D mcpl bare DELETE no WHERE",
     "DENY",
     'mcpl call supabase execute_sql \'{"query": "DELETE FROM proto_contents"}\''),

    # E. mcpl with SQL DELETE WHERE — should ALLOW
    ("E mcpl DELETE WHERE",
     "ALLOW",
     'mcpl call supabase execute_sql \'{"query": "DELETE FROM proto_contents WHERE match_id=\'X\'"}\''),

    # F. Sneaky: real rm -rf chained AFTER git commit — should DENY
    ("F chained dangerous after commit",
     "DENY",
     'git commit -m "safe" && ' + b("cm0gLXJm") + ' /tmp/x'),

    # G. Normal git push — should ALLOW
    ("G normal git push",
     "ALLOW",
     'git push origin main'),

    # H. git push --force — should DENY
    ("H force push",
     "DENY",
     'git push --force origin main'),

    # I. git push --force-with-lease — should ALLOW
    ("I force-with-lease",
     "ALLOW",
     'git push --force-with-lease origin main'),

    # J. git reset --hard — should DENY
    ("J hard reset",
     "DENY",
     'git reset --hard HEAD'),

    # K. SSH user@host — should DENY
    ("K manual ssh",
     "DENY",
     'ssh user@example.com'),

    # L. ssh-add (key management) — should ALLOW
    ("L ssh-add",
     "ALLOW",
     'ssh-add ~/.ssh/id_rsa'),

    # M. Edit tool (non-Bash) — should ALLOW (skip)
    ("M non-bash tool",
     "ALLOW",
     None),  # special: tool_name = Edit
]


def run_case(label: str, expect: str, command: str | None) -> bool:
    if command is None:
        payload: dict[str, object] = {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}}
    else:
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}

    # Isolate TMPDIR so live approval markers on the dev machine cannot
    # bleed in and flip DENY → allow.  Each run_case call gets a fresh
    # private tmpdir; no marker files are pre-created there, so the guard
    # must evaluate every pattern from scratch.
    with tempfile.TemporaryDirectory() as isolated_tmp:
        env = os.environ.copy()
        env["TMPDIR"] = isolated_tmp

        result = subprocess.run(
            ["python3", HOOK],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
        )

    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and "deny" in stdout) else "ALLOW"
    pass_fail = "PASS" if actual == expect else "FAIL"

    status_icon = "OK  " if pass_fail == "PASS" else "FAIL"
    print(f"[{status_icon}] {label:35s}  expect={expect:5s}  got={actual:5s}")
    if pass_fail == "FAIL":
        print(f"       cmd: {command!r}")
        print(f"       stdout: {stdout!r}")
    return pass_fail == "PASS"


def run_case_in_tmp(label: str, expect: str, command: str | None, isolated_tmp: str) -> bool:
    """Like run_case but uses an externally-managed tmpdir.

    The caller owns the tmpdir lifecycle, so marker files planted before
    the call are visible to the hook subprocess.
    """
    if command is None:
        payload: dict[str, object] = {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}}
    else:
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}

    env = os.environ.copy()
    env["TMPDIR"] = isolated_tmp

    result = subprocess.run(
        ["python3", HOOK],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )

    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and "deny" in stdout) else "ALLOW"
    pass_fail = "PASS" if actual == expect else "FAIL"

    status_icon = "OK  " if pass_fail == "PASS" else "FAIL"
    print(f"[{status_icon}] {label:35s}  expect={expect:5s}  got={actual:5s}")
    if pass_fail == "FAIL":
        print(f"       cmd: {command!r}")
        print(f"       stdout: {stdout!r}")
    return pass_fail == "PASS"


def _hook_marker_path(command: str, isolated_tmp: str) -> str:
    """Compute the marker path the hook would derive for this command.

    Imports the real scrub_text_arguments + _command_hash from the hook
    module so this function cannot drift from the hook's own logic.
    """
    import types
    from importlib.abc import Loader
    spec = importlib.util.spec_from_file_location("guard_destructive", HOOK)
    assert spec is not None
    raw_loader: Loader | None = spec.loader
    assert raw_loader is not None
    mod = importlib.util.module_from_spec(spec)
    assert isinstance(mod, types.ModuleType)
    raw_loader.exec_module(mod)
    scrub = getattr(mod, "scrub_text_arguments")
    hash_fn = getattr(mod, "_command_hash")
    scanned: str = scrub(command)
    cmd_hash: str = hash_fn(scanned)
    return os.path.join(isolated_tmp, f"claude-destructive-approved-{cmd_hash}.marker")


def run_raw(label: str, raw_stdin: str, expect_allow: bool, expect_advisory: bool) -> bool:
    """Feed raw (potentially garbage) stdin and check exit 0 + advisory presence."""
    with tempfile.TemporaryDirectory() as isolated_tmp:
        env = os.environ.copy()
        env["TMPDIR"] = isolated_tmp
        result = subprocess.run(
            ["python3", HOOK],
            input=raw_stdin,
            capture_output=True,
            text=True,
            env=env,
        )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    exited_zero = result.returncode == 0
    is_allow = exited_zero and "deny" not in stdout
    advisory_present = "[hook:guard-destructive] fail-open" in stderr
    ok = (is_allow == expect_allow) and (advisory_present == expect_advisory)
    icon = "OK  " if ok else "FAIL"
    print(
        f"[{icon}] {label:50s}"
        f"  allow={'Y' if is_allow else 'N'}(want={'Y' if expect_allow else 'N'})"
        f"  advisory={'Y' if advisory_present else 'N'}(want={'Y' if expect_advisory else 'N'})"
    )
    if not ok:
        print(f"       stdout: {stdout!r}")
        print(f"       stderr: {stderr!r}")
        print(f"       rc: {result.returncode}")
    return ok


def main() -> None:
    results = [run_case(*c) for c in CASES]

    # ── Advisory / fail-open cases ──────────────────────────────────────────
    # N. Garbage stdin → fail-open ALLOW + advisory on stderr
    results.append(run_raw(
        "N garbage stdin → ALLOW + advisory",
        raw_stdin="not valid json {{{{",
        expect_allow=True,
        expect_advisory=True,
    ))
    # O. Valid JSON but non-mapping (list) → _load_payload returns None → advisory
    results.append(run_raw(
        "O non-mapping JSON (list) → ALLOW + advisory",
        raw_stdin="[1, 2, 3]",
        expect_allow=True,
        expect_advisory=True,
    ))
    # P. Valid JSON, non-Bash tool_name → _bash_command returns None → advisory
    #    (shape mismatch: no "command" key, tool_name != "Bash")
    results.append(run_raw(
        "P Edit tool payload → ALLOW + advisory (shape mismatch)",
        raw_stdin=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x"}}),
        expect_allow=True,
        expect_advisory=True,
    ))
    # Q. Valid Bash tool, safe command → legit-allow, NO advisory (no spam)
    results.append(run_raw(
        "Q legit-allow safe Bash command → ALLOW + NO advisory",
        raw_stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}}),
        expect_allow=True,
        expect_advisory=False,
    ))

    # ── Hash-keyed marker tests ─────────────────────────────────────────────
    cmd_x = b("cm0gLXJm") + " /tmp/foo"
    cmd_y = "git reset --hard HEAD"

    # R. Marker authorizes only its own command (X marker → X ALLOW)
    with tempfile.TemporaryDirectory() as tmp_r:
        marker_x = _hook_marker_path(cmd_x, tmp_r)
        Path(marker_x).touch()
        results.append(run_case_in_tmp(
            "R marker authorizes its own command",
            "ALLOW",
            cmd_x,
            tmp_r,
        ))

    # S. X's marker does NOT authorize a different command Y
    with tempfile.TemporaryDirectory() as tmp_s:
        marker_x_s = _hook_marker_path(cmd_x, tmp_s)
        Path(marker_x_s).touch()
        results.append(run_case_in_tmp(
            "S marker does NOT authorize different command",
            "DENY",
            cmd_y,
            tmp_s,
        ))

    # T. Expired marker (age > TTL) → DENY
    with tempfile.TemporaryDirectory() as tmp_t:
        marker_x_t = _hook_marker_path(cmd_x, tmp_t)
        Path(marker_x_t).touch()
        # backdate mtime to 200s ago (> 120s TTL)
        old_mtime = os.path.getmtime(marker_x_t) - 200
        os.utime(marker_x_t, (old_mtime, old_mtime))
        results.append(run_case_in_tmp(
            "T expired marker (>120s) => DENY",
            "DENY",
            cmd_x,
            tmp_t,
        ))

    # U. Stale markers swept unconditionally (even on safe command)
    with tempfile.TemporaryDirectory() as tmp_u:
        bogus = os.path.join(tmp_u, "claude-destructive-approved-deadbeef.marker")
        Path(bogus).touch()
        old_u = os.path.getmtime(bogus) - 300
        os.utime(bogus, (old_u, old_u))
        # run a safe command so sweep happens without any pattern match
        run_case_in_tmp(
            "U stale sweep (safe cmd drives sweep)",
            "ALLOW",
            "git status",
            tmp_u,
        )
        swept = not os.path.exists(bogus)
        icon = "OK  " if swept else "FAIL"
        print(f"[{icon}] U stale marker was swept from disk              swept={'Y' if swept else 'N'}(want=Y)")
        results.append(swept)

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
