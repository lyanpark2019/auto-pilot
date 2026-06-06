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


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
