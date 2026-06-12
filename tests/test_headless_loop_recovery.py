"""Regression tests for headless-loop timeout recovery semantics."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parent.parent


def _args(**overrides):
    defaults = dict(
        timeout_build=10.0,
        max_cost_usd=1e9,
        max_tokens=10**12,
        per_iter_cost_estimate=0.0,
        max_concurrent_claude=10**6,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture()
def state_dir(tmp_path):
    sd = tmp_path / ".planning" / "auto-pilot"
    sd.mkdir(parents=True)
    return sd


@pytest.fixture()
def loop_module(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("headless_loop", None)
    spec_path = REPO / "scripts" / "headless-loop.py"
    spec = importlib.util.spec_from_file_location("headless_loop", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_state(state_dir: Path, payload: dict) -> None:
    (state_dir / "state.json").write_text(json.dumps(payload))


def _phase_entry(phase: int, status: str, *, ended: str | None = None) -> dict:
    return {
        "phase": phase,
        "status": status,
        "round": 1,
        "contracts": 1,
        "approved": 1,
        "started": "2026-06-12T00:00:00+00:00",
        "ended": ended,
        "commits": ["abc123"],
    }


def test_timeout_preserves_terminal_success_state(loop_module, state_dir):
    """A wrapper timeout after PM recorded success must not rewrite state to failed."""
    _write_state(state_dir, {"status": "running", "current_phase": 1, "total_phases": 2})

    def _session(prompt, log_path, timeout_sec):
        _write_state(state_dir, {
            "status": "success",
            "current_phase": 2,
            "total_phases": 2,
            "phases": [_phase_entry(2, "success", ended="2026-06-12T00:01:00+00:00")],
        })
        return 124

    with patch.object(loop_module, "run_claude_session", side_effect=_session), \
         patch.object(loop_module, "git_head", return_value="abc123"), \
         patch.object(loop_module, "stash_if_dirty") as stash:
        result = loop_module.loop_iteration(1, _args())

    assert result == "success"
    stash.assert_not_called()
    assert json.loads((state_dir / "state.json").read_text())["status"] == "success"


def test_timeout_preserves_completed_phase_when_run_continues(loop_module, state_dir):
    """A completed non-final phase should survive rc=124 so the next iteration can advance."""
    _write_state(state_dir, {"status": "running", "current_phase": 1, "total_phases": 2})

    def _session(prompt, log_path, timeout_sec):
        _write_state(state_dir, {
            "status": "running",
            "current_phase": 1,
            "total_phases": 2,
            "phases": [_phase_entry(1, "success", ended="2026-06-12T00:01:00+00:00")],
        })
        return 124

    with patch.object(loop_module, "run_claude_session", side_effect=_session), \
         patch.object(loop_module, "git_head", return_value="abc123"), \
         patch.object(loop_module, "stash_if_dirty") as stash:
        result = loop_module.loop_iteration(1, _args())

    assert result == "running"
    stash.assert_not_called()
    assert json.loads((state_dir / "state.json").read_text())["status"] == "running"


def test_phase_for_next_session_initial_state_is_phase_one(loop_module):
    assert loop_module.phase_for_next_session({"current_phase": 0, "total_phases": 2}) == 1


def test_phase_for_next_session_advances_after_completed_nonfinal_phase(loop_module):
    state = {
        "status": "running",
        "current_phase": 1,
        "total_phases": 2,
        "phases": [{"phase": 1, "status": "success", "ended": "2026-06-12T00:01:00+00:00"}],
    }

    assert loop_module.phase_for_next_session(state) == 2


def test_phase_for_next_session_keeps_running_phase(loop_module):
    state = {
        "status": "running",
        "current_phase": 1,
        "total_phases": 2,
        "phases": [{"phase": 1, "status": "running"}],
    }

    assert loop_module.phase_for_next_session(state) == 1
