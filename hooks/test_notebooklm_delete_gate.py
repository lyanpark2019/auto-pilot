#!/usr/bin/env python3
"""Test runner for notebooklm_delete_gate.sh hook.

Feeds stdin JSON payloads via subprocess in BOTH shapes the hook is wired
for in hooks/hooks.json:
  - Bash tool calls   → tool_input.command carries the CLI string
  - MCP tool calls    → tool_name = mcp__notebooklm__delete_* and tool_input
                        carries the MCP tool's own args, NO "command" key
                        (the round-2 P1 fail-open regression shape).
Deny contract: JSON permissionDecision=deny on stdout, exit 0.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).parent / "notebooklm_delete_gate.sh")

# (label, expect, payload, confirmed)
# expect: "ALLOW" (silent exit 0) or "DENY" (JSON deny output)
CASES: list[tuple[str, str, object, bool]] = [
    ("MCP delete_notebook, unconfirmed", "DENY",
     {"tool_name": "mcp__notebooklm__delete_notebook",
      "tool_input": {"notebook_id": "abc123"}}, False),
    ("MCP delete_source, unconfirmed", "DENY",
     {"tool_name": "mcp__notebooklm__delete_source",
      "tool_input": {"source_id": "s1"}}, False),
    ("MCP delete_notebook, confirmed", "ALLOW",
     {"tool_name": "mcp__notebooklm__delete_notebook",
      "tool_input": {"notebook_id": "abc123"}}, True),
    ("MCP non-delete notebooklm tool", "ALLOW",
     {"tool_name": "mcp__notebooklm__list_notebooks", "tool_input": {}}, False),
    ("Bash CLI notebook delete, unconfirmed", "DENY",
     {"tool_name": "Bash",
      "tool_input": {"command": "notebooklm notebook delete --id x"}}, False),
    ("Bash CLI nb delete, unconfirmed", "DENY",
     {"tool_name": "Bash", "tool_input": {"command": "notebooklm nb delete x"}}, False),
    ("Bash CLI notebook delete, confirmed", "ALLOW",
     {"tool_name": "Bash",
      "tool_input": {"command": "notebooklm notebook delete --id x"}}, True),
    ("Bash unrelated notebooklm command", "ALLOW",
     {"tool_name": "Bash", "tool_input": {"command": "notebooklm list --json"}}, False),
    ("garbage stdin (non-blocking default)", "ALLOW", "not json", False),
    # Case-sensitivity hardening (FIX 3): uppercase MCP tool names must DENY.
    ("MCP uppercase DELETE_notebook, unconfirmed", "DENY",
     {"tool_name": "mcp__notebooklm__DELETE_notebook",
      "tool_input": {"notebook_id": "abc123"}}, False),
    ("MCP mixed-case Delete_Source, unconfirmed", "DENY",
     {"tool_name": "mcp__notebooklm__Delete_Source",
      "tool_input": {"source_id": "s1"}}, False),
    ("MCP uppercase DELETE_notebook, confirmed", "ALLOW",
     {"tool_name": "mcp__notebooklm__DELETE_notebook",
      "tool_input": {"notebook_id": "abc123"}}, True),
    # Whitespace hardening (FIX 3): double-space CLI variants must DENY.
    ("Bash CLI double-space notebook  delete, unconfirmed", "DENY",
     {"tool_name": "Bash",
      "tool_input": {"command": "notebooklm  notebook  delete --id x"}}, False),
    ("Bash CLI double-space nb  delete, unconfirmed", "DENY",
     {"tool_name": "Bash",
      "tool_input": {"command": "notebooklm  nb  delete x"}}, False),
    ("Bash CLI double-space notebook  delete, confirmed", "ALLOW",
     {"tool_name": "Bash",
      "tool_input": {"command": "notebooklm  notebook  delete --id x"}}, True),
]


ADVISORY_TAG = "[hook:notebooklm_delete_gate] fail-open"


def run_case(label: str, expect: str, payload: object, confirmed: bool) -> bool:
    env = dict(os.environ)
    env.pop("NBM_DELETE_CONFIRMED", None)
    if confirmed:
        env["NBM_DELETE_CONFIRMED"] = "1"
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run(
        ["bash", HOOK], input=stdin, capture_output=True, text=True, env=env,
    )
    stdout = result.stdout.strip()
    actual = "DENY" if '"permissionDecision":"deny"' in stdout else "ALLOW"
    ok = actual == expect and result.returncode == 0  # deny is JSON + exit 0
    icon = "OK  " if ok else "FAIL"
    print(f"[{icon}] {label:42s} expect={expect:5s} got={actual:5s} rc={result.returncode}")
    if not ok:
        print(f"       stdout: {stdout!r}")
        print(f"       stderr: {result.stderr.strip()!r}")
    return ok


def run_advisory(
    label: str,
    raw_stdin: str,
    expect_allow: bool,
    expect_advisory: bool,
    confirmed: bool = False,
) -> bool:
    """Check fail-open advisory behavior for unparseable / valid-non-delete payloads."""
    env = dict(os.environ)
    env.pop("NBM_DELETE_CONFIRMED", None)
    if confirmed:
        env["NBM_DELETE_CONFIRMED"] = "1"
    result = subprocess.run(
        ["bash", HOOK], input=raw_stdin, capture_output=True, text=True, env=env,
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    is_allow = result.returncode == 0 and '"permissionDecision":"deny"' not in stdout
    advisory_present = ADVISORY_TAG in stderr
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
    return ok


def main() -> None:
    results = [run_case(*c) for c in CASES]

    # ── Advisory / fail-open shape tests ────────────────────────────────────
    # Unparseable stdin → fail-open ALLOW + advisory (gate must never be silently inert)
    results.append(run_advisory(
        "unparseable stdin → ALLOW + advisory",
        raw_stdin="not valid json {{{{",
        expect_allow=True,
        expect_advisory=True,
    ))
    # MCP shape delete (already in CASES via run_case) — verify advisory absent on deny
    results.append(run_advisory(
        "MCP delete unconfirmed → DENY, no advisory",
        raw_stdin=json.dumps({
            "tool_name": "mcp__notebooklm__delete_notebook",
            "tool_input": {"notebook_id": "abc123"},
        }),
        expect_allow=False,
        expect_advisory=False,
    ))
    # Valid non-delete MCP payload → legit-allow, NO advisory (no spam)
    results.append(run_advisory(
        "MCP non-delete list_notebooks → ALLOW, no advisory",
        raw_stdin=json.dumps({
            "tool_name": "mcp__notebooklm__list_notebooks",
            "tool_input": {},
        }),
        expect_allow=True,
        expect_advisory=False,
    ))
    # Valid Bash non-delete command → legit-allow, NO advisory
    results.append(run_advisory(
        "Bash non-delete command → ALLOW, no advisory",
        raw_stdin=json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "notebooklm list --json"},
        }),
        expect_allow=True,
        expect_advisory=False,
    ))
    # Bash-shape delete (already in CASES) — no advisory on a parseable delete payload
    results.append(run_advisory(
        "Bash delete unconfirmed → DENY, no advisory",
        raw_stdin=json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "notebooklm notebook delete --id x"},
        }),
        expect_allow=False,
        expect_advisory=False,
    ))

    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
