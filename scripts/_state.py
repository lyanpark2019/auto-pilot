"""Persisted auto-pilot run state — shared TypedDicts + load/save helpers.

Single source of truth for the on-disk ``state.json`` schema. Both
``orchestrator.py`` and ``headless-loop.py`` import the :class:`State` /
:class:`PhaseEntry` types from here so the wire format cannot drift between
the two scripts.

Path note: :data:`STATE_FILE` is rooted at the *current working directory*
(``Path(".planning/auto-pilot")``). ``orchestrator.py`` is invoked from the
target repo root, so this works. ``headless-loop.py`` binds its own
``STATE_FILE`` from a captured ``ROOT = Path.cwd()`` snapshot at import time
to preserve hermetic test behavior — see headless-loop.py for details.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, cast

STATE_DIR = Path(".planning/auto-pilot")
STATE_FILE = STATE_DIR / "state.json"


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


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> State:
    """Read :data:`STATE_FILE` into a :class:`State`.

    Returns:
        Parsed state dict, or an empty dict when no state file exists.
    """
    if not STATE_FILE.exists():
        return cast(State, {})
    return cast(State, json.loads(STATE_FILE.read_text()))


def save_state(state: State) -> None:
    """Persist ``state`` to :data:`STATE_FILE` (pretty-printed JSON, trailing newline).

    Args:
        state: state object to serialize. Caller owns the dict.
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
