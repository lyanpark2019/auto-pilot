"""Persisted auto-pilot run state — shared TypedDicts + load/save helpers.

Single source of truth for the on-disk ``state.json`` schema. Both
``orchestrator.py`` and ``headless-loop.py`` import the :class:`State` /
:class:`PhaseEntry` types from here so the wire format cannot drift between
the two scripts.

Concurrency: ``load_state`` and ``save_state`` cooperate via an exclusive
``flock`` on ``.planning/auto-pilot/state.lock``. Writers block readers and
each other; readers may overlap. Writes go through ``_contract.atomic_write_text``
(tempfile + fsync + rename) so even an abrupt kill leaves either the old or
new JSON, never a partial file. For an atomic read-modify-write, use
``state_transaction`` instead — it holds the exclusive lock across the entire
load → mutate → commit cycle, closing the TOCTOU window that a separate
``load_state`` + ``save_state`` pair would leave open.

Path note: :data:`STATE_FILE` is rooted at the *current working directory*
(``Path(".planning/auto-pilot")``). ``orchestrator.py`` is invoked from the
target repo root, so this works. ``headless-loop.py`` binds its own
``STATE_FILE`` from a captured ``ROOT = Path.cwd()`` snapshot at import time
to preserve hermetic test behavior — see headless-loop.py for details.
"""
from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, TypedDict, cast

import _contract

STATE_DIR = Path(".planning/auto-pilot")
STATE_FILE = STATE_DIR / "state.json"
STATE_LOCK = STATE_DIR / "state.lock"

# Loop lifecycle status values (running + the terminal set headless-loop checks).
# SoT for the terminal subset: headless-loop.py early-exit guard.
KNOWN_STATUSES = frozenset(
    {"running", "success", "failed", "stopped", "pivot-needed", "cost-cap", "time-cap"}
)


class CorruptStateError(Exception):
    """state.json parsed but violates a load-time invariant (shape or status)."""


def _validate_state(state: object) -> None:
    """Raise CorruptStateError on a clearly-corrupt parsed state.

    Conservative by design: only the top-level shape and a present ``status``
    value are checked. Keys the loop adds later are not required, so minimal
    fabricated states still load.
    """
    if not isinstance(state, dict):
        raise CorruptStateError(f"state.json must be a JSON object, got {type(state).__name__}")
    status = state.get("status")
    if status is not None and (not isinstance(status, str) or status not in KNOWN_STATUSES):
        raise CorruptStateError(
            f"state.json has unknown status {status!r}; expected one of {sorted(KNOWN_STATUSES)}"
        )


class PhaseEntry(TypedDict):
    """One element of ``state['phases']`` — a single phase's lifecycle record."""

    phase: int
    status: str
    round: int
    contracts: int
    approved: int
    started: str
    ended: str | None
    commits: list[str]


class State(TypedDict, total=False):
    """Persisted orchestrator state.

    ``total=False`` so freshly-loaded state may omit late-added fields
    (e.g. ``stopped_at`` is only present after ``stop``).
    """

    started_at: str
    spec_path: str
    current_phase: int
    total_phases: int
    status: str
    max_workers: int
    time_box_until: str | None
    phases: list[PhaseEntry]
    pivot_detector: dict[str, dict[str, int]]
    stopped_at: str
    run_id: str
    cost_usd: float
    tokens: int
    cost_cap_usd: float
    tokens_cap: int


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _state_write_lock() -> Iterator[None]:
    """Exclusive lock on ``STATE_LOCK``. Blocks until acquired."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_LOCK.touch(exist_ok=True)
    fd = STATE_LOCK.open("r+")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        finally:
            fd.close()


@contextmanager
def _state_read_lock() -> Iterator[None]:
    """Shared lock on ``STATE_LOCK``. Blocks while a writer holds it."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_LOCK.touch(exist_ok=True)
    fd = STATE_LOCK.open("r")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_SH)
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        finally:
            fd.close()


class StateTxn:
    """Handle yielded by :func:`state_transaction`.

    ``.state`` is the mutable :class:`State` dict loaded under the held
    exclusive lock (``{}`` when no state file exists).  Call :meth:`commit`
    to persist ``.state`` on context exit; without a commit nothing is written.
    """

    def __init__(self, state: State) -> None:
        self.state: State = state
        self._committed: bool = False

    def commit(self) -> None:
        """Mark the transaction dirty so :func:`state_transaction` writes on exit."""
        self._committed = True


@contextmanager
def state_transaction() -> Iterator[StateTxn]:
    """Exclusive-lock context manager that spans the full load → mutate → write cycle.

    Acquires ``fcntl.LOCK_EX`` on :data:`STATE_LOCK` before reading and holds
    it until the ``with`` body exits.  If the caller invokes
    :meth:`StateTxn.commit` inside the body, the (possibly mutated)
    ``txn.state`` is written atomically **while the lock is still held**.
    Otherwise nothing is written.

    On any exception inside the body nothing is written; the exception
    propagates normally.  The lock is always released in a ``finally`` block.

    Usage::

        with state_transaction() as txn:
            txn.state["tokens"] = txn.state.get("tokens", 0) + delta
            txn.commit()
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_LOCK.touch(exist_ok=True)
    fd = STATE_LOCK.open("r+")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        state = (
            cast(State, json.loads(STATE_FILE.read_text()))
            if STATE_FILE.exists()
            else cast(State, {})
        )
        txn = StateTxn(state)
        yield txn
        if txn._committed:
            _contract.atomic_write_text(
                STATE_FILE, json.dumps(txn.state, indent=2) + "\n"
            )
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        finally:
            fd.close()


def load_state() -> State:
    """Read :data:`STATE_FILE` into a :class:`State` under a shared lock.

    Returns:
        Parsed state dict, or an empty dict when no state file exists.
    """
    if not STATE_FILE.exists():
        return cast(State, {})
    with _state_read_lock():
        parsed = json.loads(STATE_FILE.read_text())
    _validate_state(parsed)
    return cast(State, parsed)


def save_state(state: State) -> None:
    """Persist ``state`` to :data:`STATE_FILE` atomically under an exclusive lock.

    Args:
        state: state object to serialize. Caller owns the dict.
    """
    payload = json.dumps(state, indent=2) + "\n"
    with _state_write_lock():
        _contract.atomic_write_text(STATE_FILE, payload)
