"""Parallel-safe subagent dispatch wrapper.

PM env-injection (os.environ[...] = ...) is process-global and would race
with concurrent reviewer dispatches. This wrapper spawns each reviewer as
a `claude -p` subprocess with an ISOLATED env dict — no shared state.

Hook (`pre-reviewer-write.sh`) reads AUTO_PILOT_SUBAGENT_ROLE +
AUTO_PILOT_OUTPUT_DIR from the spawned env; each subprocess sees only
its own.

Spawn-prompt scope (decided 2026-06, round-2 W1-7): the prompt stays a
minimal pointer (ticket path + sha-refusal tripwire) ON PURPOSE — the
ticket file is the single instruction source; duplicating instructions
into the prompt would create a second drifting copy. Reviewer liveness
is the watchdog's job (soft/hard timeouts in _dispatch), not the prompt's.

Watchdog coverage note (ⓓ-6, 2026-06 round-2 W2):
  Soft warning fires at SOFT_WARN_SEC (default 300 s).
  Hard kill fires at HARD_KILL_SEC (default 480 s):
    → proc.terminate() → 10 s grace → proc.kill()
  One retry respawn of that reviewer follows; retry failure → structured
  ReviewerFailure sentinel (NOT an unhandled exception) so the PM can
  surface the failure and dispatch an alternate reviewer.

COVERAGE LIMIT: this module covers the subprocess workflow path only.
Interactive review dispatch (Agent tool) is out of scope — mitigation is
codex exec Bash timeout + Task deadline (residual risk documented here).
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

SOFT_WARN_SEC = 300
HARD_KILL_SEC = 480
KILL_GRACE_SEC = 10

logger = logging.getLogger(__name__)


class SpawnTimeoutError(Exception):
    """A spawned reviewer did not produce done.marker within timeout."""


@dataclass
class ReviewerFailure:
    """Structured signal returned when a reviewer fails after one retry.

    The PM should surface this to dispatch an alternate reviewer rather
    than silently substituting a model or aborting the whole round.

    Fields:
        role:   reviewer role string (e.g. ``"codex-reviewer"``).
        reason: human-readable reason (``"hard-kill"`` | ``"retry-hard-kill"``
                | ``"retry-exit-<code>"``).
    """
    role: str
    reason: str


@dataclass
class SpawnHandle:
    role: str
    ticket: Path
    output_dir: Path
    proc: subprocess.Popen[bytes]
    # Spawn inputs retained verbatim so _respawn can reconstruct the exact
    # call without an untyped **kwargs blob (each kept as its real type).
    allowed_tools: str = field(default="", repr=False)
    disallowed_tools: str = field(default="", repr=False)

    def poll(self) -> int | None:
        return self.proc.poll()


def spawn(*, role: str, ticket: Path, output_dir: Path,
          allowed_tools: str, disallowed_tools: str) -> SpawnHandle:
    """Spawn a `claude -p` subprocess for one reviewer dispatch.

    Subprocess env contains:
      - AUTO_PILOT_SUBAGENT_ROLE=<role>     (read by pre-reviewer-write.sh)
      - AUTO_PILOT_OUTPUT_DIR=<output_dir>  (read by pre-reviewer-write.sh)
    Parent env is NOT mutated.

    `--allowedTools` / `--disallowedTools` are real Claude Code CLI flags
    that constrain tool surface for this invocation only.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    # Allowlist approach considered but rejected: `claude` and `codex` consume opaque
    # vendor env vars (CLAUDE_*, ANTHROPIC_*, OPENAI_*, model-router vars) that are not
    # fully enumerated in any public contract.  Maintaining an allowlist would silently
    # break spawned reviewers whenever a new vendor var is introduced.
    # Decision: denylist of secrets that reviewer subprocesses provably do not need.
    # Residual risk: secrets added outside this list still pass through — see module docstring.
    _ENV_DENYLIST = frozenset({
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "GCP_SERVICE_ACCOUNT_KEY",
        "GITHUB_TOKEN",
        "NPM_TOKEN",
        "PYPI_TOKEN",
        "SLACK_TOKEN",
        "STRIPE_SECRET_KEY",
        "DATABASE_URL",
        "POSTGRES_PASSWORD",
        "MYSQL_PASSWORD",
        "REDIS_URL",
    })
    env = {
        k: v for k, v in os.environ.items() if k not in _ENV_DENYLIST
    }
    env["AUTO_PILOT_SUBAGENT_ROLE"] = role
    env["AUTO_PILOT_OUTPUT_DIR"] = str(output_dir)
    prompt = f"TICKET={ticket}\nRead ticket. Refuse if ticket_sha mismatch."
    cmd = [
        "claude", "-p",
        "--allowedTools", allowed_tools,
        "--disallowedTools", disallowed_tools,
        prompt,
    ]
    proc = subprocess.Popen(cmd, env=env)
    return SpawnHandle(role=role, ticket=ticket, output_dir=output_dir,
                       proc=proc, allowed_tools=allowed_tools,
                       disallowed_tools=disallowed_tools)


def _respawn(handle: SpawnHandle) -> SpawnHandle:
    """Re-invoke spawn with the same parameters as the original handle."""
    return spawn(
        role=handle.role,
        ticket=handle.ticket,
        output_dir=handle.output_dir,
        allowed_tools=handle.allowed_tools,
        disallowed_tools=handle.disallowed_tools,
    )


def _hard_kill(proc: subprocess.Popen[bytes], role: str) -> None:
    """terminate → wait 10 s → kill."""
    logger.warning("watchdog: hard-killing reviewer %s (pid=%s)", role, proc.pid)
    proc.terminate()
    try:
        proc.wait(timeout=KILL_GRACE_SEC)
    except subprocess.TimeoutExpired:
        logger.warning("watchdog: SIGKILL reviewer %s (pid=%s)", role, proc.pid)
        proc.kill()
        proc.wait()


def wait_all(
    handles: list[SpawnHandle],
    *,
    timeout_sec: int,
    soft_warn_sec: int = SOFT_WARN_SEC,
    hard_kill_sec: int = HARD_KILL_SEC,
) -> list[ReviewerFailure]:
    """Poll done.marker for every handle until all present, or timeout.

    Implements the two-tier watchdog:
      - soft warning at ``soft_warn_sec`` (default 300 s): logs per-laggard warning,
        process continues running — no kill.
      - hard kill at ``hard_kill_sec`` (default 480 s): terminate → grace → kill →
        ONE retry respawn; retry failure → :class:`ReviewerFailure` appended to
        return list.

    The original ``timeout_sec`` parameter becomes the outer wall-clock cap after
    which any still-remaining handles that were NOT already hard-killed raise
    :class:`SpawnTimeoutError` (same semantics as before for non-watchdog consumers).

    Returns:
        List of :class:`ReviewerFailure` for reviewers that failed after retry.
        Empty list = all reviewers completed successfully.

    Raises:
        SpawnTimeoutError: if ``timeout_sec`` elapses for handles not yet
            handled by the hard-kill/retry path.
    """
    start = time.time()
    deadline = start + timeout_sec
    soft_warn_deadline = start + soft_warn_sec
    hard_kill_deadline = start + hard_kill_sec

    # Track per-handle state
    warned: set[str] = set()
    killed: set[str] = set()
    retrying: dict[str, SpawnHandle] = {}  # role → retry handle
    retry_started: dict[str, float] = {}   # role → respawn wall-clock
    failures: list[ReviewerFailure] = []
    # Map role → original handle (roles must be unique)
    by_role: dict[str, SpawnHandle] = {h.role: h for h in handles}
    remaining: set[str] = set(by_role.keys())

    while remaining:
        now = time.time()

        for role in list(remaining):
            # ── retry handle path (takes priority over original) ──────────
            if role in retrying:
                retry_h = retrying[role]
                if (retry_h.output_dir / "done.marker").exists():
                    remaining.discard(role)
                    retrying.pop(role, None)
                    continue
                retry_exited = retry_h.poll() is not None
                if retry_exited:
                    # Give a brief poll for a late-written marker
                    time.sleep(0.05)
                    if (retry_h.output_dir / "done.marker").exists():
                        remaining.discard(role)
                        retrying.pop(role, None)
                        continue
                    # Retry truly failed without a marker
                    failures.append(
                        ReviewerFailure(role=role, reason=f"retry-exit-{retry_h.poll()}")
                    )
                    remaining.discard(role)
                    retrying.pop(role, None)
                    continue
                # Bound the retry like the original (review r1: an unbounded hung
                # retry leaked an orphan subprocess and surfaced as the outer
                # SpawnTimeoutError instead of a structured failure).
                if now - retry_started.get(role, now) > hard_kill_sec:
                    _hard_kill(retry_h.proc, role)
                    failures.append(ReviewerFailure(role=role, reason="retry-hard-kill"))
                    remaining.discard(role)
                    retrying.pop(role, None)
                continue  # skip original handle checks while retry is live

            # ── original handle ───────────────────────────────────────────
            h = by_role[role]
            marker = h.output_dir / "done.marker"

            if marker.exists():
                remaining.discard(role)
                continue

            exited = h.poll() is not None

            # ── hard-kill window ──────────────────────────────────────────
            if now > hard_kill_deadline and role not in killed:
                if not exited:
                    _hard_kill(h.proc, role)
                killed.add(role)
                # Attempt one retry respawn
                logger.warning("watchdog: respawning reviewer %s after hard kill", role)
                retry_h = _respawn(by_role[role])
                retrying[role] = retry_h
                retry_started[role] = time.time()
                continue

            # ── soft-warn window ─────────────────────────────────────────
            if now > soft_warn_deadline and role not in warned and role not in killed:
                logger.warning(
                    "watchdog: reviewer %s lagging (%.0fs elapsed, soft-warn threshold=%ds)",
                    role, now - start, soft_warn_sec,
                )
                warned.add(role)

            # ── exited without marker (before hard-kill window) ──────────
            if exited and not marker.exists():
                # Original wait_all semantics: proc exited without marker = done
                remaining.discard(role)
                continue

        if not remaining:
            break
        if time.time() > deadline:
            roles = list(remaining)
            # Kill anything still alive before raising — never leave orphans.
            # (getattr: test fakes may expose poll() without a real proc)
            for role in roles:
                candidate: SpawnHandle | None
                for candidate in (retrying.get(role), by_role.get(role)):
                    if candidate is not None and candidate.poll() is None:
                        proc = getattr(candidate, "proc", None)
                        if proc is not None:
                            _hard_kill(proc, role)
            raise SpawnTimeoutError(
                f"timed out waiting for done.marker from {roles}"
            )
        time.sleep(0.1)

    return failures
