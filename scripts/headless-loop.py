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
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import cast

import _config
import _prompts
from _log import event
from _state import State

ROOT = Path.cwd()
# NB: local STATE_FILE binds to this loop's ROOT snapshot (captured at import
# time). We do not use _state.STATE_FILE because the hermetic test harness
# reloads this module per-test with a tmp cwd; _state.STATE_FILE is resolved
# lazily relative to the *runtime* cwd and would diverge.
STATE_DIR = ROOT / ".planning" / "auto-pilot"
STATE_FILE = STATE_DIR / "state.json"
LOG_DIR = STATE_DIR / "logs"

CONFIG = _config.load()
CLAUDE_BIN = CONFIG.claude_bin
HEADLESS_ENV = CONFIG.headless_env

HEADLESS_PROMPT_PREAMBLE = _prompts.load("headless")


def load_state() -> State:
    """Read this loop's ``STATE_FILE`` into a :class:`State`.

    A local override of :func:`_state.load_state` that uses ``STATE_FILE``
    bound to this module's ``ROOT`` snapshot (see note on STATE_FILE).

    Returns:
        Parsed state, or an empty dict when the file is missing.
    """
    if not STATE_FILE.exists():
        return cast(State, {})
    return cast(State, json.loads(STATE_FILE.read_text()))


def git_head() -> str:
    """Return the current ``HEAD`` SHA of the repo at ``ROOT``.

    Raises:
        subprocess.CalledProcessError: when ``git rev-parse`` fails (e.g. not a
            git repo, detached state with no commits).
    """
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
    ).strip()


def git_reset_hard(sha: str) -> None:
    """Hard-reset the working tree at ``ROOT`` to ``sha``.

    Args:
        sha: target commit. Caller is responsible for ensuring it exists.
    """
    subprocess.run(["git", "reset", "--hard", sha], cwd=str(ROOT), check=True)


def commit_trailer(iter_n: int, phase: int) -> str:
    """Build the git trailer block embedding iteration + phase numbers.

    Args:
        iter_n: outer-loop iteration index.
        phase: current phase number.

    Returns:
        Trailer string suitable for appending to a commit message body.
    """
    return f"\n\nauto-pilot-iter: {iter_n}\nauto-pilot-phase: {phase}\n"


def run_claude_session(prompt: str, log_path: Path, timeout_sec: float) -> int:
    """Spawn a headless ``claude -p`` session and stream its output to a log.

    Args:
        prompt: user prompt body; the ``HEADLESS_PROMPT_PREAMBLE`` is prepended.
        log_path: where to tee stdout+stderr. Parent dirs are created.
        timeout_sec: kill the subprocess if it runs longer than this.

    Returns:
        The subprocess return code on normal exit, or ``124`` when the timer
        fired (mirroring coreutils ``timeout``).
    """
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
            event("session.timeout", timeout_s=int(timeout_sec))
            lf.write(f"\n[TIMEOUT] killed after {timeout_sec:.0f}s\n")
            lf.flush()
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except (OSError, subprocess.SubprocessError):
                # proc may already be dead or PID reused; nothing to recover.
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
    """Run one PM cycle and return the final ``state.status`` for it.

    On timeout (return code 124) or post-run ``status == "failed"``, hard-resets
    the working tree to the pre-iteration HEAD so failed phases leave no trace.

    Args:
        iter_n: 1-based outer-loop iteration index.
        args: parsed CLI namespace; expects ``timeout_build``.

    Returns:
        Final status string (``"running"``, ``"success"``, ``"failed"``,
        ``"stopped"``, or ``"pivot-needed"``).
    """
    state = load_state()
    if not state:
        event("loop.state_missing")
        return "failed"

    current_status = state.get("status")
    if current_status in {"success", "stopped", "pivot-needed", "failed"}:
        assert current_status is not None  # narrowed by membership check above
        return current_status

    phase = state.get("current_phase", 0)
    pre_head = git_head()
    event("iter.start", n=iter_n, phase=phase, pre_head=pre_head[:8])

    log = LOG_DIR / f"iter-{iter_n:04d}-phase-{phase}.log"
    prompt = _prompts.render("iteration", iter_n=iter_n, phase=phase)

    rc = run_claude_session(prompt, log, args.timeout_build)

    if rc == 124:
        event("iter.timeout_rollback", pre_head=pre_head[:8])
        git_reset_hard(pre_head)
        return "failed"

    new_state = load_state()
    status = new_state.get("status", "running")

    if status == "failed":
        event("iter.fail_rollback", pre_head=pre_head[:8])
        git_reset_hard(pre_head)

    return status


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the headless driver loop.

    Args:
        argv: optional argv list (defaults to ``sys.argv[1:]``).

    Returns:
        ``0`` for normal completion (success or max-iter exhausted), ``1`` when
        the loop ends in a non-success terminal status, ``2`` when no state
        file exists.
    """
    p = argparse.ArgumentParser(prog="auto-pilot-headless")
    p.add_argument("--max-iter", type=int, default=CONFIG.default_max_iter)
    p.add_argument(
        "--sleep",
        type=int,
        default=CONFIG.default_sleep_sec,
        help="seconds between iterations",
    )
    p.add_argument(
        "--timeout-build",
        type=float,
        default=CONFIG.default_timeout_build_sec,
        help="per-iteration claude session timeout (s)",
    )
    p.add_argument("--once", action="store_true", help="run one iteration and exit (smoke test)")
    args = p.parse_args(argv)

    if not STATE_FILE.exists():
        event("loop.no_state_file")
        return 2

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    for n in range(1, args.max_iter + 1):
        status = loop_iteration(n, args)
        event("iter.end", n=n, status=status)

        if status in {"success", "stopped", "pivot-needed", "failed"}:
            event("loop.terminal", status=status)
            return 0 if status == "success" else 1

        if args.once:
            event("loop.once_exit")
            return 0

        time.sleep(args.sleep)

    event("loop.max_iter_reached", max_iter=args.max_iter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
