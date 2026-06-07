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

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from _log import event

SOFT_WARN_SEC = 300
HARD_KILL_SEC = 480
KILL_GRACE_SEC = 10
_PROGRESS_INTERVAL_TICKS = 300  # 300 × 0.1 s = 30 s between progress events


@runtime_checkable
class SpawnHandleProtocol(Protocol):
    """Structural type accepted by :func:`wait_all`.

    Concrete :class:`SpawnHandle` satisfies this Protocol. Tests substitute
    lightweight in-process fakes (see ``test_reviewer_wrapper.py:55`` and
    ``test_beta_watchdog.py:23``) that also satisfy it — the Protocol makes
    that contract explicit.

    Note: :func:`_respawn` needs the full :class:`SpawnHandle` (``ticket``,
    ``allowed_tools``, ``disallowed_tools``); callers that pass fakes must
    ensure the hard-kill respawn path is never exercised (e.g. by setting
    ``hard_kill_sec`` beyond the test window).
    """

    role: str
    output_dir: Path
    proc: subprocess.Popen[bytes]

    def poll(self) -> int | None: ...


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
    event("watchdog.hard_kill", role=role, pid=proc.pid)
    proc.terminate()
    try:
        proc.wait(timeout=KILL_GRACE_SEC)
    except subprocess.TimeoutExpired:
        event("watchdog.sigkill", role=role, pid=proc.pid,
              error_type="TimeoutExpired")
        proc.kill()
        proc.wait()


def _poll_retry_handle(
    role: str,
    retrying: dict[str, SpawnHandleProtocol],
    retry_started: dict[str, float],
    remaining: set[str],
    failures: list[ReviewerFailure],
    hard_kill_sec: int,
    now: float,
) -> None:
    """Advance one poll tick for an in-flight retry handle."""
    retry_h = retrying[role]
    if (retry_h.output_dir / "done.marker").exists():
        remaining.discard(role)
        retrying.pop(role, None)
        return
    retry_exited = retry_h.poll() is not None
    if retry_exited:
        time.sleep(0.05)
        if (retry_h.output_dir / "done.marker").exists():
            remaining.discard(role)
            retrying.pop(role, None)
            return
        failures.append(ReviewerFailure(role=role, reason=f"retry-exit-{retry_h.poll()}"))
        remaining.discard(role)
        retrying.pop(role, None)
        return
    if now - retry_started.get(role, now) > hard_kill_sec:
        _hard_kill(retry_h.proc, role)
        failures.append(ReviewerFailure(role=role, reason="retry-hard-kill"))
        remaining.discard(role)
        retrying.pop(role, None)


def _poll_original_handle(
    role: str,
    h: SpawnHandleProtocol,
    by_role: dict[str, SpawnHandleProtocol],
    killed: set[str],
    warned: set[str],
    retrying: dict[str, SpawnHandleProtocol],
    retry_started: dict[str, float],
    remaining: set[str],
    hard_kill_deadline: float,
    soft_warn_deadline: float,
    start: float,
    soft_warn_sec: int,
    now: float,
) -> None:
    """Advance one poll tick for an original (non-retry) handle."""
    marker = h.output_dir / "done.marker"
    if marker.exists():
        remaining.discard(role)
        return
    exited = h.poll() is not None
    if now > hard_kill_deadline and role not in killed:
        if not exited:
            _hard_kill(h.proc, role)
        killed.add(role)
        event("watchdog.respawn", role=role)
        retry_h = _respawn(cast(SpawnHandle, by_role[role]))
        retrying[role] = retry_h
        retry_started[role] = time.time()
        return
    if now > soft_warn_deadline and role not in warned and role not in killed:
        event("watchdog.reviewer_lagging", role=role,
              elapsed_s=int(now - start), soft_warn_threshold_s=soft_warn_sec)
        warned.add(role)
    if exited and not marker.exists():
        remaining.discard(role)


def _drain_remaining(
    remaining: set[str],
    retrying: dict[str, SpawnHandleProtocol],
    by_role: dict[str, SpawnHandleProtocol],
    deadline: float,
) -> None:
    """Kill orphan subprocesses and raise SpawnTimeoutError for outstanding roles."""
    roles = list(remaining)
    for role in roles:
        candidate: SpawnHandleProtocol | None
        for candidate in (retrying.get(role), by_role.get(role)):
            if candidate is not None and candidate.poll() is None:
                proc = getattr(candidate, "proc", None)
                if proc is not None:
                    _hard_kill(proc, role)
    raise SpawnTimeoutError(f"timed out waiting for done.marker from {roles}")


def _tick_all_roles(
    remaining: set[str],
    by_role: dict[str, SpawnHandleProtocol],
    retrying: dict[str, SpawnHandleProtocol],
    retry_started: dict[str, float],
    killed: set[str],
    warned: set[str],
    failures: list[ReviewerFailure],
    hard_kill_sec: int,
    hard_kill_deadline: float,
    soft_warn_deadline: float,
    start: float,
    soft_warn_sec: int,
) -> None:
    """Advance one poll tick for all remaining roles."""
    now = time.time()
    for role in list(remaining):
        if role in retrying:
            _poll_retry_handle(role, retrying, retry_started, remaining,
                               failures, hard_kill_sec, now)
            continue
        _poll_original_handle(role, by_role[role], by_role, killed, warned,
                               retrying, retry_started, remaining,
                               hard_kill_deadline, soft_warn_deadline,
                               start, soft_warn_sec, now)


def wait_all(
    handles: list[SpawnHandleProtocol],
    *,
    timeout_sec: int,
    soft_warn_sec: int = SOFT_WARN_SEC,
    hard_kill_sec: int = HARD_KILL_SEC,
) -> list[ReviewerFailure]:
    """Poll done.marker for every handle until all present, or timeout.

    Two-tier watchdog: soft warning at ``soft_warn_sec`` (log only); hard kill
    at ``hard_kill_sec`` (terminate→grace→kill→one retry); retry failure →
    :class:`ReviewerFailure` in the return list.  ``timeout_sec`` is the outer
    wall-clock cap; unhandled remaining handles raise :class:`SpawnTimeoutError`.

    Returns empty list on success. Raises SpawnTimeoutError on timeout.
    """
    start = time.time()
    deadline = start + timeout_sec
    soft_warn_deadline = start + soft_warn_sec
    hard_kill_deadline = start + hard_kill_sec
    warned: set[str] = set()
    killed: set[str] = set()
    retrying: dict[str, SpawnHandleProtocol] = {}
    retry_started: dict[str, float] = {}
    failures: list[ReviewerFailure] = []
    by_role: dict[str, SpawnHandleProtocol] = {h.role: h for h in handles}
    remaining: set[str] = set(by_role.keys())
    tick = 0
    while remaining:
        _tick_all_roles(remaining, by_role, retrying, retry_started, killed,
                        warned, failures, hard_kill_sec, hard_kill_deadline,
                        soft_warn_deadline, start, soft_warn_sec)
        if not remaining:
            break
        if time.time() > deadline:
            _drain_remaining(remaining, retrying, by_role, deadline)
        tick += 1
        if tick % _PROGRESS_INTERVAL_TICKS == 0:
            event("wait_all.progress",
                  waited_s=int(time.time() - start),
                  outstanding=sorted(remaining))
        time.sleep(0.1)
    return failures
