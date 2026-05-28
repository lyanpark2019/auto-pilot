"""Shared terminal-status enum for worker output classification."""
from __future__ import annotations

from enum import Enum


class WorkerStatus(str, Enum):
    DONE       = "DONE"
    DONE_NOOP  = "DONE_NOOP"
    BLOCKED    = "BLOCKED"
    FAILED     = "FAILED"
    CANCELED   = "CANCELED"
    PARTIAL    = "PARTIAL"   # non-terminal; reaper treats as in-flight


TERMINAL: frozenset[WorkerStatus] = frozenset({
    WorkerStatus.DONE,
    WorkerStatus.DONE_NOOP,
    WorkerStatus.BLOCKED,
    WorkerStatus.FAILED,
    WorkerStatus.CANCELED,
})
