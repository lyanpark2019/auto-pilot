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
]


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


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
