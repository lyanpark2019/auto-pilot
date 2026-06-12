#!/usr/bin/env python3
"""Self-test for dispatch-contract-gate.sh reviewer fail-closed branch.

Runs the hook via subprocess with crafted Task tool payloads + a temp cwd that
optionally holds an active-run state.json. ALLOW = silent/exit0 (no "deny" in
stdout); DENY = JSON with permissionDecision deny.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "dispatch-contract-gate.sh")


def _running_state(cwd: Path) -> None:
    sd = cwd / ".planning" / "auto-pilot"
    sd.mkdir(parents=True)
    (sd / "state.json").write_text(json.dumps({"status": "running"}))


def run_case(label, subagent_type, prompt, active_run, expect) -> bool:
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        if active_run:
            _running_state(cwd)
        payload = {"tool_name": "Task",
                   "tool_input": {"subagent_type": subagent_type, "prompt": prompt}}
        result = subprocess.run(["bash", HOOK], input=json.dumps(payload),
                                capture_output=True, text=True, cwd=cwd,
                                env={**os.environ, "PATH": os.environ["PATH"]})
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and "deny" in stdout) else "ALLOW"
    ok = actual == expect
    print(f"[{'OK  ' if ok else 'FAIL'}] {label:48s} expect={expect:5s} got={actual:5s}")
    if not ok:
        print(f"       stdout={stdout!r} stderr={result.stderr.strip()!r}")
    return ok


CASES = [
    ("reviewer, no ticket, active run", "auto-pilot-codex-reviewer", "review this diff", True, "DENY"),
    ("reviewer, no ticket, NO active run", "auto-pilot-codex-reviewer", "review this diff", False, "ALLOW"),
    ("reviewer WITH ticket, active run", "auto-pilot-claude-reviewer",
     "TICKET=" "/tmp/x/tickets/claude-reviewer.json review", True, "ALLOW"),
    ("non-reviewer (general-purpose), active run", "general-purpose", "do work", True, "ALLOW"),
    ("tech-critic-lead, active run", "tech-critic-lead", "gate contract", True, "ALLOW"),
]


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
