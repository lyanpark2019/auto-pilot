"""Tests for headless-loop.py — mock subprocess + git so no real claude session runs."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def state_dir(tmp_path):
    """Create the fake state directory under tmp_path/.planning/auto-pilot/."""
    sd = tmp_path / ".planning" / "auto-pilot"
    sd.mkdir(parents=True)
    return sd


@pytest.fixture()
def loop_module(tmp_path, monkeypatch):
    """Import headless_loop fresh with ROOT pointing at tmp_path.

    headless-loop.py captures ROOT = Path.cwd() at import time, so we chdir
    first and reload the module to bind ROOT/STATE_DIR/STATE_FILE/LOG_DIR
    to the per-test tmp_path.
    """
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("headless_loop", None)
    spec_path = REPO / "scripts" / "headless-loop.py"
    spec = importlib.util.spec_from_file_location("headless_loop", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_state(state_dir: Path, status: str = "running", current_phase: int = 1) -> None:
    (state_dir / "state.json").write_text(
        json.dumps({
            "status": status,
            "current_phase": current_phase,
            "total_phases": 3,
        })
    )


def test_terminal_state_short_circuits(loop_module, state_dir):
    """When state.status is already terminal, loop_iteration returns it without spawning a session."""
    _write_state(state_dir, status="success")
    args = MagicMock(timeout_build=10.0)
    with patch.object(loop_module, "run_claude_session") as rcs, \
         patch.object(loop_module, "git_head", return_value="deadbeef"), \
         patch.object(loop_module, "git_reset_hard") as reset:
        result = loop_module.loop_iteration(1, args)
    assert result == "success"
    rcs.assert_not_called()
    reset.assert_not_called()


def test_pivot_needed_short_circuits(loop_module, state_dir):
    """pivot-needed is also a terminal status — no session, no rollback."""
    _write_state(state_dir, status="pivot-needed")
    args = MagicMock(timeout_build=10.0)
    with patch.object(loop_module, "run_claude_session") as rcs, \
         patch.object(loop_module, "git_reset_hard") as reset:
        result = loop_module.loop_iteration(1, args)
    assert result == "pivot-needed"
    rcs.assert_not_called()
    reset.assert_not_called()


def test_missing_state_returns_failed(loop_module, tmp_path):
    """When state.json doesn't exist, loop_iteration returns 'failed' immediately."""
    # No state.json written — the .planning/auto-pilot/ dir doesn't even exist.
    args = MagicMock(timeout_build=10.0)
    with patch.object(loop_module, "run_claude_session") as rcs, \
         patch.object(loop_module, "git_head") as ghead:
        result = loop_module.loop_iteration(1, args)
    assert result == "failed"
    rcs.assert_not_called()
    ghead.assert_not_called()


def test_success_path_returns_running(loop_module, state_dir):
    """When session returns 0 and stub leaves state non-terminal, status remains 'running'."""
    _write_state(state_dir, status="running")
    args = MagicMock(timeout_build=10.0)
    with patch.object(loop_module, "run_claude_session", return_value=0), \
         patch.object(loop_module, "git_head", return_value="cafef00d"), \
         patch.object(loop_module, "git_reset_hard") as reset:
        result = loop_module.loop_iteration(1, args)
    assert result == "running"
    reset.assert_not_called()


def test_timeout_triggers_rollback(loop_module, state_dir):
    """When run_claude_session returns 124, loop_iteration resets HEAD and returns 'failed'."""
    _write_state(state_dir, status="running")
    args = MagicMock(timeout_build=10.0)
    with patch.object(loop_module, "run_claude_session", return_value=124), \
         patch.object(loop_module, "git_head", return_value="cafef00d"), \
         patch.object(loop_module, "git_reset_hard") as reset:
        result = loop_module.loop_iteration(1, args)
    assert result == "failed"
    reset.assert_called_once_with("cafef00d")


def test_failed_status_triggers_rollback(loop_module, state_dir):
    """When session returns 0 but mutates state.status='failed', loop_iteration rolls back."""
    _write_state(state_dir, status="running")
    args = MagicMock(timeout_build=10.0)

    def _session(prompt, log_path, timeout_sec):
        # Simulate a worker writing state.json with status=failed.
        (state_dir / "state.json").write_text(
            json.dumps({
                "status": "failed",
                "current_phase": 1,
                "total_phases": 3,
            })
        )
        return 0

    with patch.object(loop_module, "run_claude_session", side_effect=_session), \
         patch.object(loop_module, "git_head", return_value="abc123"), \
         patch.object(loop_module, "git_reset_hard") as reset:
        result = loop_module.loop_iteration(1, args)
    assert result == "failed"
    reset.assert_called_once_with("abc123")


def test_session_success_status_no_rollback(loop_module, state_dir):
    """When session mutates state to 'success', loop_iteration returns 'success' with no rollback."""
    _write_state(state_dir, status="running")
    args = MagicMock(timeout_build=10.0)

    def _session(prompt, log_path, timeout_sec):
        (state_dir / "state.json").write_text(
            json.dumps({
                "status": "success",
                "current_phase": 3,
                "total_phases": 3,
            })
        )
        return 0

    with patch.object(loop_module, "run_claude_session", side_effect=_session), \
         patch.object(loop_module, "git_head", return_value="abc123"), \
         patch.object(loop_module, "git_reset_hard") as reset:
        result = loop_module.loop_iteration(1, args)
    assert result == "success"
    reset.assert_not_called()
