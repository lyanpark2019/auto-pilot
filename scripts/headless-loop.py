#!/usr/bin/env python3
"""auto-pilot headless infinite loop.

Drives a real autonomous PM loop by spawning `claude -p --dangerously-skip-permissions`
subprocess sessions, one per loop step. Each session is fully headless: stdin is
DEVNULL, env carries HARNESS_HEADLESS=1 so the skill auto-skips all user prompts.

Adapted from cc-system run-server.py (greatSumini, MIT) — kept its iter-id +
rollback-on-fail pattern, dropped its ideation step (auto-pilot uses spec phases
instead), added phase-aware verify and pivot detection.

Per loop iteration:
  1. snapshot pre-phase HEAD
  2. spawn `claude -p` headless session running `/auto-pilot start --phase N`
  3. on session exit:
       - status=success → commit + advance phase
       - status=fail    → `git reset --hard <pre-phase-HEAD>`, mark pivot-needed, stop
       - status=pivot-needed → stop (no rollback — partial work may be committed)
  4. sleep N seconds (default 10)
  5. exit when state.json status in {success, stopped, pivot-needed, failed}

Usage:
  python headless-loop.py            # current dir, default settings
  python headless-loop.py --max-iter 50 --sleep 30 --timeout-build 14400
  python headless-loop.py --once     # one iteration then exit (smoke test)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
STATE_DIR = ROOT / ".planning" / "auto-pilot"
STATE_FILE = STATE_DIR / "state.json"
LOG_DIR = STATE_DIR / "logs"

CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"

HEADLESS_ENV = {"HARNESS_HEADLESS": "1", "AUTO_PILOT_HEADLESS": "1"}

HEADLESS_PROMPT_PREAMBLE = """**[HEADLESS MODE — auto-pilot server]**

First action: run `echo "HEADLESS=${HARNESS_HEADLESS:-0}"`.

If `HEADLESS=1` (it will be), this session is a non-interactive auto-pilot worker.
Rules:
- Never call AskUserQuestion. Never wait for confirmation.
- If a skill or subagent says "ask the user", use the most reasonable default and proceed.
- stdin is /dev/null — there is no one to answer.
- Stop conditions are state.json driven, not user driven.

---

"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text())


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()


def git_reset_hard(sha: str) -> None:
    subprocess.run(["git", "reset", "--hard", sha], cwd=str(ROOT), check=True)


def commit_trailer(iter_n: int, phase: int) -> str:
    return f"\n\nauto-pilot-iter: {iter_n}\nauto-pilot-phase: {phase}\n"


def run_claude_session(prompt: str, log_path: Path, timeout_sec: float) -> int:
    full_prompt = HEADLESS_PROMPT_PREAMBLE + prompt
    cmd = [CLAUDE_BIN, "-p", "--dangerously-skip-permissions", full_prompt]
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as lf:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, **HEADLESS_ENV},
        )

        hit_timeout = {"v": False}

        def _on_timeout() -> None:
            hit_timeout["v"] = True
            sys.stderr.write(f"\n[TIMEOUT] killing claude session after {timeout_sec:.0f}s\n")
            lf.write(f"\n[TIMEOUT] killed after {timeout_sec:.0f}s\n")
            lf.flush()
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass

        timer = threading.Timer(timeout_sec, _on_timeout)
        timer.daemon = True
        timer.start()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                lf.write(line)
                lf.flush()
            proc.wait()
        finally:
            timer.cancel()

        if hit_timeout["v"]:
            return 124
        return proc.returncode


def loop_iteration(iter_n: int, args: argparse.Namespace) -> str:
    """Run one PM cycle. Return final state.status for this iteration."""
    state = load_state()
    if not state:
        sys.stderr.write("ERROR: state.json missing — run `/auto-pilot start` first to init.\n")
        return "failed"

    if state.get("status") in {"success", "stopped", "pivot-needed", "failed"}:
        return state["status"]

    phase = state.get("current_phase", 0)
    pre_head = git_head()
    sys.stderr.write(f"\n=== iter {iter_n} | phase {phase} | pre-HEAD {pre_head[:8]} ===\n")

    log = LOG_DIR / f"iter-{iter_n:04d}-phase-{phase}.log"
    prompt = (
        f"You are resuming the auto-pilot loop. Iteration {iter_n}, phase {phase}.\n\n"
        f"Run the `auto-pilot` skill: read state.json, plan contracts, dispatch workers + dual reviewers,\n"
        f"verify, commit with trailers `auto-pilot-iter: {iter_n}` and `auto-pilot-phase: {phase}`,\n"
        f"advance phase. STOP this session after one phase completes (do not loop in-session — the\n"
        f"outer headless-loop.py drives the next iteration).\n\n"
        f"On any unrecoverable error, update state.json status to 'failed' before exiting."
    )

    rc = run_claude_session(prompt, log, args.timeout_build)

    if rc == 124:
        sys.stderr.write(f"[TIMEOUT] rolling back to {pre_head[:8]}\n")
        git_reset_hard(pre_head)
        return "failed"

    new_state = load_state()
    status = new_state.get("status", "running")

    if status == "failed":
        sys.stderr.write(f"[FAIL] rolling back to {pre_head[:8]}\n")
        git_reset_hard(pre_head)

    return status


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="auto-pilot-headless")
    p.add_argument("--max-iter", type=int, default=100)
    p.add_argument("--sleep", type=int, default=10, help="seconds between iterations")
    p.add_argument("--timeout-build", type=float, default=4 * 3600, help="per-iteration claude session timeout (s)")
    p.add_argument("--once", action="store_true", help="run one iteration and exit (smoke test)")
    args = p.parse_args(argv)

    if not STATE_FILE.exists():
        sys.stderr.write("auto-pilot: no state.json — run `/auto-pilot start` first to initialize.\n")
        return 2

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    for n in range(1, args.max_iter + 1):
        status = loop_iteration(n, args)
        sys.stderr.write(f"--- iter {n} ended with status={status} ---\n")

        if status in {"success", "stopped", "pivot-needed", "failed"}:
            sys.stderr.write(f"auto-pilot: terminal status '{status}' — exiting loop\n")
            return 0 if status == "success" else 1

        if args.once:
            sys.stderr.write("--once: exit after first iteration\n")
            return 0

        time.sleep(args.sleep)

    sys.stderr.write(f"auto-pilot: max-iter {args.max_iter} reached, exiting\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
