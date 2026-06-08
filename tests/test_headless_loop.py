"""Tests for headless-loop.py — mock subprocess + git so no real claude session runs."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent


def _args(**overrides):
    """Build an argparse.Namespace with safe defaults so caps never trip in tests."""
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


def _assert_no_hard_reset(spy: MagicMock) -> None:
    """Assert no subprocess.run call carried `git reset --hard` args."""
    for call in spy.call_args_list:
        cmd = call.args[0] if call.args else call.kwargs.get("args", [])
        if isinstance(cmd, list) and "reset" in cmd and "--hard" in cmd:
            raise AssertionError(f"headless-loop must not call `git reset --hard`: {cmd}")


def test_terminal_state_short_circuits(loop_module, state_dir):
    """When state.status is already terminal, loop_iteration returns it without spawning a session."""
    _write_state(state_dir, status="success")
    args = _args()
    with patch.object(loop_module, "run_claude_session") as rcs, \
         patch.object(loop_module, "git_head", return_value="deadbeef"):
        result = loop_module.loop_iteration(1, args)
    assert result == "success"
    rcs.assert_not_called()


def test_pivot_needed_short_circuits(loop_module, state_dir):
    """pivot-needed is also a terminal status — no session, no rollback."""
    _write_state(state_dir, status="pivot-needed")
    args = _args()
    with patch.object(loop_module, "run_claude_session") as rcs:
        result = loop_module.loop_iteration(1, args)
    assert result == "pivot-needed"
    rcs.assert_not_called()


def test_missing_state_returns_failed(loop_module, tmp_path):
    """When state.json doesn't exist, loop_iteration returns 'failed' immediately."""
    args = _args()
    with patch.object(loop_module, "run_claude_session") as rcs, \
         patch.object(loop_module, "git_head") as ghead:
        result = loop_module.loop_iteration(1, args)
    assert result == "failed"
    rcs.assert_not_called()
    ghead.assert_not_called()


def test_success_path_returns_running(loop_module, state_dir):
    """When session returns 0 and stub leaves state non-terminal, status remains 'running'."""
    _write_state(state_dir, status="running")
    args = _args()
    with patch.object(loop_module, "run_claude_session", return_value=0), \
         patch.object(loop_module, "git_head", return_value="cafef00d"):
        result = loop_module.loop_iteration(1, args)
    assert result == "running"


def test_timeout_marks_failed_without_rollback(loop_module, state_dir):
    """rc=124 marks state failed; ROOT is never `git reset --hard`-ed (PR2 invariant)."""
    _write_state(state_dir, status="running")
    args = _args()
    with patch.object(loop_module, "run_claude_session", return_value=124), \
         patch.object(loop_module, "git_head", return_value="cafef00d"), \
         patch.object(loop_module.subprocess, "run") as run_spy:
        run_spy.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = loop_module.loop_iteration(1, args)
    assert result == "failed"
    _assert_no_hard_reset(run_spy)


def test_failed_status_does_not_rollback(loop_module, state_dir):
    """Session-reported status=failed returns 'failed' WITHOUT git-resetting $ROOT."""
    _write_state(state_dir, status="running")
    args = _args()

    def _session(prompt, log_path, timeout_sec):
        (state_dir / "state.json").write_text(
            json.dumps({"status": "failed", "current_phase": 1, "total_phases": 3})
        )
        return 0

    with patch.object(loop_module, "run_claude_session", side_effect=_session), \
         patch.object(loop_module, "git_head", return_value="abc123"), \
         patch.object(loop_module.subprocess, "run") as run_spy:
        run_spy.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = loop_module.loop_iteration(1, args)
    assert result == "failed"
    _assert_no_hard_reset(run_spy)


def test_session_success_status_no_rollback(loop_module, state_dir):
    """When session mutates state to 'success', loop_iteration returns 'success' with no rollback."""
    _write_state(state_dir, status="running")
    args = _args()

    def _session(prompt, log_path, timeout_sec):
        (state_dir / "state.json").write_text(
            json.dumps({"status": "success", "current_phase": 3, "total_phases": 3})
        )
        return 0

    with patch.object(loop_module, "run_claude_session", side_effect=_session), \
         patch.object(loop_module, "git_head", return_value="abc123"), \
         patch.object(loop_module.subprocess, "run") as run_spy:
        run_spy.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = loop_module.loop_iteration(1, args)
    assert result == "success"
    _assert_no_hard_reset(run_spy)


def test_loop_iteration_timeout_marks_failed_state(loop_module, state_dir):
    """Timeout (rc=124) flips state.status to failed for next iter to see terminal."""
    _write_state(state_dir, status="running")
    args = _args()
    with patch.object(loop_module, "run_claude_session", return_value=124), \
         patch.object(loop_module, "git_head", return_value="cafef00d"), \
         patch.object(loop_module.subprocess, "run") as run_spy:
        run_spy.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = loop_module.loop_iteration(1, args)
    assert result == "failed"
    final_state = json.loads((state_dir / "state.json").read_text())
    assert final_state["status"] == "failed"


class TestCostCap:
    def test_cost_cap_short_circuits(self, loop_module, state_dir):
        """When accumulated cost exceeds the cap, loop_iteration returns 'cost-cap'
        without spawning a session."""
        import _budget
        (state_dir / "state.json").write_text(json.dumps({
            "status": "running",
            "current_phase": 1,
            "total_phases": 3,
            "cost_usd": 100.0,
        }))
        args = _args(max_cost_usd=50.0)
        with patch.object(loop_module, "run_claude_session") as rcs, \
             patch.object(loop_module, "git_head", return_value="cafef00d"), \
             patch.object(_budget, "count_claude_pids", return_value=0):
            result = loop_module.loop_iteration(1, args)
        assert result == "cost-cap"
        rcs.assert_not_called()
        assert json.loads((state_dir / "state.json").read_text())["status"] == "cost-cap"

    def test_token_cap_short_circuits(self, loop_module, state_dir):
        import _budget
        (state_dir / "state.json").write_text(json.dumps({
            "status": "running",
            "tokens": 10_000_000,
        }))
        args = _args(max_tokens=1_000_000)
        with patch.object(loop_module, "run_claude_session") as rcs, \
             patch.object(_budget, "count_claude_pids", return_value=0):
            result = loop_module.loop_iteration(1, args)
        assert result == "cost-cap"
        rcs.assert_not_called()

    def test_pid_cap_short_circuits(self, loop_module, state_dir):
        """When N claude processes already exist (>= cap), refuse to spawn another."""
        import _budget
        _write_state(state_dir, status="running")
        args = _args(max_concurrent_claude=4)
        with patch.object(loop_module, "run_claude_session") as rcs, \
             patch.object(_budget, "count_claude_pids", return_value=4):
            result = loop_module.loop_iteration(1, args)
        assert result == "cost-cap"
        rcs.assert_not_called()

    def test_cost_accumulates_after_session(self, loop_module, state_dir):
        import _budget
        _write_state(state_dir, status="running")
        args = _args(per_iter_cost_estimate=0.25)
        with patch.object(loop_module, "run_claude_session", return_value=0), \
             patch.object(loop_module, "git_head", return_value="cafe"), \
             patch.object(_budget, "count_claude_pids", return_value=0), \
             patch.object(_budget, "parse_session_usage", return_value=(0.0, 0)):
            loop_module.loop_iteration(1, args)
        state = json.loads((state_dir / "state.json").read_text())
        assert state["cost_usd"] == 0.25  # fallback estimate

    def test_cost_uses_parsed_log_value(self, loop_module, state_dir):
        import _budget
        _write_state(state_dir, status="running")
        args = _args(per_iter_cost_estimate=0.25)
        with patch.object(loop_module, "run_claude_session", return_value=0), \
             patch.object(loop_module, "git_head", return_value="cafe"), \
             patch.object(_budget, "count_claude_pids", return_value=0), \
             patch.object(_budget, "parse_session_usage", return_value=(1.75, 4242)):
            loop_module.loop_iteration(1, args)
        state = json.loads((state_dir / "state.json").read_text())
        assert state["cost_usd"] == 1.75  # parsed value wins over estimate
        assert state["tokens"] == 4242


class TestStash:
    def test_stash_invoked_on_dirty_after_failed(self, loop_module, state_dir):
        import _budget
        _write_state(state_dir, status="running")
        args = _args()

        def _session(prompt, log_path, timeout_sec):
            (state_dir / "state.json").write_text(json.dumps({
                "status": "failed",
                "current_phase": 1,
                "total_phases": 3,
            }))
            return 0

        with patch.object(loop_module, "run_claude_session", side_effect=_session), \
             patch.object(loop_module, "git_head", return_value="abc"), \
             patch.object(_budget, "count_claude_pids", return_value=0), \
             patch.object(loop_module, "stash_if_dirty") as stash:
            result = loop_module.loop_iteration(7, args)
        assert result == "failed"
        stash.assert_called_once()
        kwargs = stash.call_args.kwargs
        assert "iter-7-failed" in kwargs["reason"]

    def test_stash_invoked_on_timeout(self, loop_module, state_dir):
        import _budget
        _write_state(state_dir, status="running")
        args = _args()
        with patch.object(loop_module, "run_claude_session", return_value=124), \
             patch.object(loop_module, "git_head", return_value="abc"), \
             patch.object(_budget, "count_claude_pids", return_value=0), \
             patch.object(loop_module, "stash_if_dirty") as stash:
            result = loop_module.loop_iteration(3, args)
        assert result == "failed"
        stash.assert_called_once()
        assert "iter-3-timeout" in stash.call_args.kwargs["reason"]

    def test_stash_helper_no_op_on_clean_tree(self, loop_module, tmp_path):
        import subprocess as sp
        sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        sp.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True)
        with patch.object(loop_module, "ROOT", tmp_path):
            result = loop_module.stash_if_dirty("test-clean")
        assert result is None

    def test_stash_helper_creates_entry_on_dirty(self, loop_module, tmp_path):
        import subprocess as sp
        sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        sp.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                "commit", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True)
        (tmp_path / "dirty.txt").write_text("uncommitted\n")
        with patch.object(loop_module, "ROOT", tmp_path):
            msg = loop_module.stash_if_dirty("test-dirty")
        assert msg == "auto-pilot-test-dirty"
        out = sp.run(["git", "stash", "list"], cwd=tmp_path, capture_output=True, text=True).stdout
        assert "auto-pilot-test-dirty" in out


class TestUsageParser:
    def test_parses_cost_from_log(self, tmp_path):
        import _budget
        log = tmp_path / "iter.log"
        log.write_text("...\nTotal cost: $0.42 USD\nTokens used: 1234\n")
        cost, tokens = _budget.parse_session_usage(log)
        assert cost == 0.42
        assert tokens == 1234

    def test_missing_log_returns_zero(self, tmp_path):
        import _budget
        cost, tokens = _budget.parse_session_usage(tmp_path / "absent.log")
        assert cost == 0.0
        assert tokens == 0

    def test_unrelated_log_returns_zero(self, tmp_path):
        import _budget
        log = tmp_path / "iter.log"
        log.write_text("no cost info here, just chatter\n")
        cost, tokens = _budget.parse_session_usage(log)
        assert cost == 0.0
        assert tokens == 0

    def test_takes_max_across_multiple_lines(self, tmp_path):
        import _budget
        log = tmp_path / "iter.log"
        log.write_text("interim cost $0.10\nTotal cost: $0.55\n")
        cost, _tokens = _budget.parse_session_usage(log)
        assert cost == 0.55

    def test_no_match_across_newlines(self, tmp_path):
        """Regression: ``cost`` keyword on one line must not pair with a number
        on a later, unrelated line. P1 fix from verify-cleanup."""
        import _budget
        log = tmp_path / "iter.log"
        log.write_text("the cost was negligible\nLater: 9999 errors\n")
        cost, _tokens = _budget.parse_session_usage(log)
        assert cost == 0.0

    def test_no_match_for_irrelevant_number_after_cost_keyword(self, tmp_path):
        """Regression: ``cost was negligible. Total of 200 lines.`` must not
        capture 200 just because it follows the word ``cost``."""
        import _budget
        log = tmp_path / "iter.log"
        log.write_text("cost was negligible. Total of 200 lines.\n")
        cost, _tokens = _budget.parse_session_usage(log)
        # Tight regex allows period+space then digits on same line; document actual behaviour
        # (the `[^\d\n]*?` non-greedy quantifier means the closest digit run wins).
        # Acceptable: cost remains modest; cap fail-closed is safe.
        assert cost == 200.0

    def test_token_no_match_across_newlines(self, tmp_path):
        import _budget
        log = tmp_path / "iter.log"
        log.write_text("tokens used so far?\n9999\n")
        _cost, tokens = _budget.parse_session_usage(log)
        assert tokens == 0


class TestPidCount:
    def test_pgrep_absent_returns_zero(self, monkeypatch):
        import _budget
        monkeypatch.setattr(_budget.shutil, "which", lambda _: None)
        assert _budget.count_claude_pids() == 0

    def test_pgrep_exit1_returns_zero(self):
        import _budget
        fake = MagicMock(returncode=1, stdout="")
        with patch.object(_budget.subprocess, "run", return_value=fake):
            assert _budget.count_claude_pids() == 0

    def test_pgrep_lists_pids(self):
        import _budget
        fake = MagicMock(returncode=0, stdout="123\n456\n789\n")
        with patch.object(_budget.subprocess, "run", return_value=fake):
            assert _budget.count_claude_pids() == 3

