#!/usr/bin/env python3
"""Self-test for headless-sync-dispatch-guard.sh."""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).parent / "headless-sync-dispatch-guard.sh")


def run_case(label: str, headless: bool, tool_name: str,
             run_in_background: bool | None, expect: str) -> bool:
    payload = {"tool_name": tool_name,
               "tool_input": {"run_in_background": run_in_background, "prompt": "x", "command": "x"}}
    env = os.environ.copy()
    env.pop("HARNESS_HEADLESS", None)
    if headless:
        env["HARNESS_HEADLESS"] = "1"
    result = subprocess.run(["bash", HOOK], input=json.dumps(payload),
                            capture_output=True, text=True, env=env)
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and "deny" in stdout) else "ALLOW"
    ok = actual == expect
    print(f"[{'OK  ' if ok else 'FAIL'}] {label:46s} expect={expect:5s} got={actual:5s}")
    if not ok:
        print(f"       stdout={stdout!r} stderr={result.stderr.strip()!r}")
    return ok


CASES = [
    ("headless + background Task", True, "Task", True, "DENY"),
    ("headless + foreground Task", True, "Task", False, "ALLOW"),
    ("headless + background Bash", True, "Bash", True, "DENY"),
    ("NOT headless + background Task", False, "Task", True, "ALLOW"),
    ("headless + no bg field Task", True, "Task", None, "ALLOW"),
]


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
