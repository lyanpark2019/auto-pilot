#!/usr/bin/env python3
"""Self-test for dispatch-contract-gate.sh reviewer fail-closed branch.

Runs the hook via subprocess with crafted Task tool payloads + a temp cwd that
optionally holds an active-run state.json and/or a real validated contract tree.
ALLOW = silent/exit0 (no "deny" in stdout); DENY = JSON permissionDecision deny.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HOOK = str(Path(__file__).parent / "dispatch-contract-gate.sh")


def _running_state(cwd: Path) -> None:
    sd = cwd / ".planning" / "auto-pilot"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "state.json").write_text(json.dumps({"status": "running"}))


def _real_contract(cwd: Path) -> str:
    """Build a valid contract tree the hook's strong path accepts; return ticket path."""
    base = cwd / ".planning" / "auto-pilot"
    contract_dir = base / "contracts" / "phase-1"
    tickets_dir = contract_dir / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    contract_json = contract_dir / "contract.json"
    contract_json.write_text(json.dumps({"id": "phase-1", "phase": "1", "scope": []}))
    sha = hashlib.sha256(contract_json.read_bytes()).hexdigest()
    (contract_dir / "contract-check.json").write_text(json.dumps({"contract_sha256": sha}))
    ticket_path = tickets_dir / "claude-reviewer.json"
    ticket_path.write_text("{}")
    preflight_dir = base / "preflight"
    preflight_dir.mkdir(parents=True, exist_ok=True)
    (preflight_dir / "phase-1.json").write_text(json.dumps({
        "generated_ts": datetime.now(timezone.utc).isoformat(),
        "head_sha": "",  # empty → head-mismatch check skipped (cwd is not a git repo anyway)
    }))
    return str(ticket_path)


def run_case(label: str, subagent_type: str, prompt: str | None,
             active_run: bool, build_contract: bool, expect: str) -> bool:
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        if active_run:
            _running_state(cwd)
        if build_contract:
            prompt = "TICKET=" + _real_contract(cwd) + " review"
        payload = {"tool_name": "Task",
                   "tool_input": {"subagent_type": subagent_type, "prompt": prompt}}
        result = subprocess.run(["bash", HOOK], input=json.dumps(payload),
                                capture_output=True, text=True, cwd=cwd,
                                env={**os.environ, "PATH": os.environ["PATH"]})
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and "deny" in stdout) else "ALLOW"
    ok = actual == expect
    print(f"[{'OK  ' if ok else 'FAIL'}] {label:52s} expect={expect:5s} got={actual:5s}")
    if not ok:
        print(f"       stdout={stdout!r} stderr={result.stderr.strip()!r}")
    return ok


# label, subagent_type, prompt, active_run, build_contract, expect
CASES = [
    ("reviewer, no marker, active run", "auto-pilot-codex-reviewer", "review this diff", True, False, "DENY"),
    ("reviewer, no marker, NO active run", "auto-pilot-codex-reviewer", "review this diff", False, False, "ALLOW"),
    ("reviewer, REAL contract+ticket, active run", "auto-pilot-claude-reviewer", None, True, True, "ALLOW"),
    ("reviewer, ticket path but NO contract.json", "auto-pilot-claude-reviewer",
     "TICKET=" + "/tmp/nope/tickets/claude-reviewer.json review", True, False, "DENY"),
    ("non-reviewer general-purpose, active run", "general-purpose", "do work", True, False, "ALLOW"),
    ("tech-critic-lead, active run", "tech-critic-lead", "gate contract", True, False, "ALLOW"),
]


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
