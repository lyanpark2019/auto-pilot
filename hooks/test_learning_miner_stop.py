#!/usr/bin/env python3
"""Test runner for learning-miner-stop.sh Stop hook.

Feeds Stop-payload JSON via stdin with HOME pointed at a temp dir so the durable
home ledger is never touched.  The target repo root is supplied two ways the
hook supports — CLAUDE_PROJECT_DIR (repo standard) or the payload's `cwd`.
Advisory contract: exit 0 on every path; the miner runs (writes a ticket under
the temp home ledger) ONLY when an auto-pilot run is detected (state.json
present) and the payload is not a Stop reentry.
"""
import glob
import json
import os
import site
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "learning-miner-stop.sh")

# Overriding HOME (to isolate the durable ledger) also hides Python's user-site
# (`$HOME/.local/...`), where deps like `referencing` may be pip-installed.
# Restore it on PYTHONPATH for the miner subprocess so import resolution matches
# production (which runs with the real HOME).  Ledger path still honors tmp HOME.
_USER_SITE = site.getusersitepackages()


def _seed_run(root: Path, *, finding: bool) -> None:
    planning = root / ".planning" / "auto-pilot"
    planning.mkdir(parents=True, exist_ok=True)
    (planning / "state.json").write_text(json.dumps({"run_id": "rTEST"}))
    if finding:
        (planning / "critic-rejections-phase-1.jsonl").write_text(
            json.dumps(
                {
                    "file": "scripts/foo.py",
                    "issue": "bare except swallows error",
                    "candidate_asset": "hook",
                }
            )
            + "\n"
        )


def _ledger_files(home: Path, root: Path) -> list[str]:
    slug = str(root.resolve()).replace("/", "-")
    improvements = home / ".claude" / "projects" / slug / "improvements"
    return glob.glob(str(improvements / "*.json"))


# (label, expect_ran, payload, seed_state, seed_finding, root_via)
#   root_via "env": set CLAUDE_PROJECT_DIR=root
#   root_via "cwd": unset CLAUDE_PROJECT_DIR, inject {"cwd": root} into payload
CASES: list[tuple[str, bool, object, bool, bool, str]] = [
    ("reentry guard (stop_hook_active)", False, {"stop_hook_active": True}, True, True, "env"),
    ("no state.json -> no-op", False, {}, False, False, "env"),
    ("active run (env root) -> writes ticket", True, {}, True, True, "env"),
    ("active run (payload cwd) -> writes ticket", True, {}, True, True, "cwd"),
    ("garbage stdin -> fail-open, no run", False, "not json at all", False, False, "env"),
]


def run_case(
    label: str,
    expect_ran: bool,
    payload: object,
    seed_state: bool,
    seed_finding: bool,
    root_via: str,
) -> bool:
    with tempfile.TemporaryDirectory() as home_s, tempfile.TemporaryDirectory() as root_s:
        home = Path(home_s)
        root = Path(root_s)
        if seed_state:
            _seed_run(root, finding=seed_finding)
        env = dict(os.environ)
        env["HOME"] = str(home)
        if _USER_SITE:
            env["PYTHONPATH"] = _USER_SITE + os.pathsep + env.get("PYTHONPATH", "")
        env.pop("CLAUDE_PROJECT_DIR", None)
        if root_via == "env":
            env["CLAUDE_PROJECT_DIR"] = str(root)
            stdin_payload = payload
        else:  # "cwd": root comes from the payload, env unset
            stdin_payload = dict(payload) if isinstance(payload, dict) else payload
            if isinstance(stdin_payload, dict):
                stdin_payload["cwd"] = str(root)
        stdin = stdin_payload if isinstance(stdin_payload, str) else json.dumps(stdin_payload)
        result = subprocess.run(
            ["bash", HOOK], input=stdin, capture_output=True, text=True, env=env
        )
        ran = len(_ledger_files(home, root)) > 0
        ok = result.returncode == 0 and ran == expect_ran
    icon = "OK  " if ok else "FAIL"
    print(
        f"[{icon}] {label:44s} expect_ran={str(expect_ran):5s} "
        f"got_ran={str(ran):5s} rc={result.returncode}"
    )
    if not ok:
        print(f"       stdout: {result.stdout.strip()!r}")
        print(f"       stderr: {result.stderr.strip()!r}")
    return ok


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
