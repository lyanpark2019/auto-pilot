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
import re
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
    """Represent SpawnHandle data for this module."""
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


# --- Env filtering: DEFAULT-DENY ALLOWLIST (2026-06-10 security re-audit) ----
# A name-denylist can never enumerate every secret naming convention, so the
# prior denylist+regex leaked ~50% of common secret env vars (STRIPE_SK, PAT,
# KUBECONFIG, MONGODB_URI, JWT, AWS_ACCESS_KEY_ID, …) into the reviewer
# subprocess. We now forward ONLY a known-safe operational set and drop
# everything else by default. This is the permanent fix per the
# anti-whack-a-mole rule (stop chasing secret names; allow only what runs).
#
# The reviewer is a `claude -p` subprocess (see _reviewer_cmd / spawn). It
# authenticates via HOME (~/.claude config), NOT via an API key — proven by
# ANTHROPIC_API_KEY already being stripped today while reviewers keep working.
# So the allowlist only needs what a CLI process + claude config discovery
# require; no credential env var is needed.

_ALLOWED_ENV_EXACT = frozenset({
    "PATH",     # locate `claude` and any tool it shells out to
    "HOME",     # claude reads ~/.claude config + auth from here (live auth path)
    "USER",     # some CLIs read it for config / temp paths
    "LOGNAME",  # POSIX login name; same role as USER for some tools
    "SHELL",    # subprocess/tooling that spawns a shell
    "TERM",     # terminal capabilities for any TTY-aware output
    "TMPDIR",   # scratch dir for claude + child processes
    "TMP",      # Windows/alt scratch dir alias
    "TEMP",     # Windows/alt scratch dir alias
    "LANG",     # locale → correct UTF-8 text handling
    "PWD",      # working-directory awareness for relative paths
    "COLUMNS",  # terminal width for formatted output
    "LINES",    # terminal height for formatted output
    "EDITOR",   # tools that may invoke an editor
})

# Prefix allowlist: families of operational vars whose exact names vary.
_ALLOWED_ENV_PREFIXES = (
    "LC_",          # locale categories (LC_ALL, LC_CTYPE, …)
    "AUTO_PILOT_",  # our own dispatch contract vars (role/output re-set below)
    "CLAUDE_",      # claude runtime/config (e.g. CLAUDE_CONFIG_DIR)
    "CLAUDECODE",   # claude-code runtime marker (CLAUDECODE, CLAUDE_CODE_*)
    "XDG_",         # config/cache dir discovery (XDG_CONFIG_HOME, …)
)

# Secondary defense-in-depth FLOOR applied AFTER the allowlist: even a var that
# survives by prefix (e.g. CLAUDE_API_TOKEN, AUTO_PILOT_SECRET) is dropped if
# its name matches a secret-class pattern. Belt and suspenders — the allowlist
# is primary, this catches an allowlisted-prefix var that smells like a secret.
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

_SECRET_RE = re.compile(
    r"(?i)(SECRET|TOKEN|PASSWORD|KEY$|CREDENTIAL|^GH_CLIENT|DATABASE_URL|REDIS_URL)"
)


def _reviewer_env(role: str, output_dir: Path) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if (k in _ALLOWED_ENV_EXACT or k.startswith(_ALLOWED_ENV_PREFIXES))
        and k not in _ENV_DENYLIST
        and not _SECRET_RE.search(k)
    }
    env["AUTO_PILOT_SUBAGENT_ROLE"] = role
    env["AUTO_PILOT_OUTPUT_DIR"] = str(output_dir)
    return env


def _reviewer_cmd(ticket: Path, allowed_tools: str, disallowed_tools: str) -> list[str]:
    prompt = f"TICKET={ticket}\nRead ticket. Refuse if ticket_sha mismatch."
    return [
        "claude", "-p",
        "--allowedTools", allowed_tools,
        "--disallowedTools", disallowed_tools,
        prompt,
    ]


def spawn(*, role: str, ticket: Path, output_dir: Path,
          allowed_tools: str, disallowed_tools: str) -> SpawnHandle:
    """Spawn a `claude -p` subprocess for one reviewer dispatch."""
    output_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        _reviewer_cmd(ticket, allowed_tools, disallowed_tools),
        env=_reviewer_env(role, output_dir),
    )
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
    """Poll reviewer done markers with soft warning, hard kill, and one retry."""
    start = time.time()
    deadline, soft_warn_deadline = start + timeout_sec, start + soft_warn_sec
    hard_kill_deadline = start + hard_kill_sec
    warned: set[str] = set()
    killed: set[str] = set()
    retrying: dict[str, SpawnHandleProtocol] = {}
    retry_started: dict[str, float] = {}
    failures: list[ReviewerFailure] = []
    by_role: dict[str, SpawnHandleProtocol] = {h.role: h for h in handles}
    remaining: set[str] = set(by_role)
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
