"""Tests for scripts/_status.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _status  # noqa: E402


def test_worker_status_values():
    assert _status.WorkerStatus.DONE.value == "DONE"
    assert _status.WorkerStatus.DONE_NOOP.value == "DONE_NOOP"
    assert _status.WorkerStatus.BLOCKED.value == "BLOCKED"
    assert _status.WorkerStatus.FAILED.value == "FAILED"
    assert _status.WorkerStatus.CANCELED.value == "CANCELED"
    assert _status.WorkerStatus.PARTIAL.value == "PARTIAL"


def test_terminal_set():
    assert _status.WorkerStatus.PARTIAL not in _status.TERMINAL
    assert _status.WorkerStatus.DONE in _status.TERMINAL
    assert _status.WorkerStatus.DONE_NOOP in _status.TERMINAL
    assert _status.WorkerStatus.BLOCKED in _status.TERMINAL
    assert _status.WorkerStatus.FAILED in _status.TERMINAL
    assert _status.WorkerStatus.CANCELED in _status.TERMINAL


def test_terminal_is_all_but_partial():
    assert _status.TERMINAL == frozenset(_status.WorkerStatus) - {_status.WorkerStatus.PARTIAL}


def test_worker_status_is_str():
    assert isinstance(_status.WorkerStatus.DONE, str)
    # str-mixin equality: artifact strings compare directly against members
    assert _status.WorkerStatus.DONE == "DONE"
    assert "DONE" == _status.WorkerStatus.DONE
