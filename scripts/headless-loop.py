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
  2. spawn `claude -p` headless session (prompts/iteration.md prose trigger: 'Run the auto-pilot skill', phase N)
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
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import _budget
import _config
import _prompts
from _log import event
from _state import STATE_DIR, STATE_FILE, load_state, save_state

# ROOT captured at import time; used only for subprocess cwd (git ops + claude
# session). State + log paths come from _state and resolve lazily relative to
# cwd at call time — the C6 hermetic test fixture monkeypatch.chdir's into
# tmp_path before invoking loop_iteration, so every state/log read+write lands
# under tmp_path as intended.
ROOT = Path.cwd()
LOG_DIR = STATE_DIR / "logs"

CONFIG = _config.load()
CLAUDE_BIN = CONFIG.claude_bin
HEADLESS_ENV = CONFIG.headless_env

HEADLESS_PROMPT_PREAMBLE = _prompts.load("headless")


def git_head() -> str:
    """Return the current ``HEAD`` SHA of the repo at ``ROOT``.

    Raises:
        subprocess.CalledProcessError: when ``git rev-parse`` fails (e.g. not a
            git repo, detached state with no commits).
    """
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True, timeout=30
    ).strip()


def stash_if_dirty(reason: str) -> str | None:
    """If ``$ROOT`` has uncommitted changes, stash them with a recoverable label.

    Returns the stash message on success, ``None`` when the tree was clean (or
    when ``git stash`` exits non-zero). Non-destructive — caller can recover
    via ``git stash list | grep <reason>``.

    Args:
        reason: short tag embedded in the stash message.
    """
    porcelain = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if not porcelain.stdout.strip():
        return None
    msg = f"auto-pilot-{reason}"
    res = subprocess.run(
        ["git", "stash", "push", "-u", "-m", msg],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if res.returncode != 0:
        event("stash.failed", reason=reason, stderr=res.stderr.strip()[:200])
        return None
    event("stash.created", reason=reason, msg=msg)
    return msg


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
    if current_status in {"success", "stopped", "pivot-needed", "failed", "cost-cap"}:
        assert current_status is not None  # narrowed by membership check above
        return current_status

    cap_hit = _budget.check_caps(args, state)
    if cap_hit is not None:
        state["status"] = cap_hit
        save_state(state)
        return cap_hit

    phase = state.get("current_phase", 0)
    pre_head = git_head()
    event("iter.start", n=iter_n, phase=phase, pre_head=pre_head[:8])

    log = LOG_DIR / f"iter-{iter_n:04d}-phase-{phase}.log"
    prompt = _prompts.render("iteration", iter_n=iter_n, phase=phase)

    rc = run_claude_session(prompt, log, args.timeout_build)

    # Accumulate cost + tokens regardless of exit code (best-effort)
    log_cost, log_tokens = _budget.parse_session_usage(log)
    if log_cost <= 0.0:
        log_cost = args.per_iter_cost_estimate
    state_after = load_state() or state
    state_after["cost_usd"] = float(state_after.get("cost_usd", 0.0)) + log_cost
    state_after["tokens"] = int(state_after.get("tokens", 0)) + log_tokens
    save_state(state_after)

    if rc == 124:
        event("iter.timeout_no_root_reset",
              pre_head=pre_head[:8],
              note="state.status set to failed; $ROOT untouched")
        stash_if_dirty(reason=f"iter-{iter_n}-timeout")
        state2 = load_state()
        state2["status"] = "failed"
        save_state(state2)
        return "failed"

    new_state = load_state()
    status = new_state.get("status", "running")

    if status == "failed":
        event("iter.fail_no_root_reset",
              note="per PR2: $ROOT untouched on phase fail; worktree cleanup is the recovery unit")
        stash_if_dirty(reason=f"iter-{iter_n}-failed")

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
    p.add_argument(
        "--max-cost-usd",
        type=float,
        default=CONFIG.default_max_cost_usd,
        help="abort run when accumulated cost exceeds this (USD)",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=CONFIG.default_max_tokens,
        help="abort run when accumulated tokens exceed this",
    )
    p.add_argument(
        "--per-iter-cost-estimate",
        type=float,
        default=CONFIG.default_per_iter_cost_estimate_usd,
        help="fallback per-iter cost (USD) used when claude log lacks a total",
    )
    p.add_argument(
        "--max-concurrent-claude",
        type=int,
        default=CONFIG.default_max_concurrent_claude,
        help="abort spawn when this many claude processes are already running",
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

        if status in {"success", "stopped", "pivot-needed", "failed", "cost-cap"}:
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
