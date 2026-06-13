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


def test_main_runs_recovery_once_at_startup(loop_module, state_dir) -> None:
    """main() calls _recover.run_recovery exactly once before the iteration loop."""
    from unittest.mock import MagicMock

    (state_dir / "state.json").write_text(json.dumps({
        "status": "running",
        "current_phase": 1,
        "total_phases": 3,
    }))

    recovery_mock = MagicMock(
        return_value={"reaped": [], "stale_am_cleared": False, "stale_am_error": None}
    )

    with patch.object(loop_module._recover, "run_recovery", recovery_mock), \
         patch.object(loop_module, "run_claude_session", return_value=0), \
         patch.object(loop_module, "git_head", return_value="abc123"), \
         patch.object(loop_module, "stash_if_dirty", return_value=None):
        loop_module.main(["--once"])

    assert recovery_mock.call_count == 1


class TestSessionCommand:
    def test_production_cmd_requests_stream_json(self, loop_module, tmp_path):
        """C2: the real claude -p invocation must ask for stream-json output so
        the budget parser sees structured ``{type:result}`` totals in prod."""
        captured: dict[str, list[str]] = {}

        class _FakeProc:
            returncode = 0
            stdout = iter(())

            def wait(self, timeout: float | None = None) -> int:
                return 0

        def _fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            return _FakeProc()

        log = tmp_path / "s.log"
        with patch.object(loop_module.subprocess, "Popen", side_effect=_fake_popen):
            loop_module.run_claude_session("do thing", log, 10.0)
        cmd = captured["cmd"]
        assert "--output-format" in cmd
        assert cmd[cmd.index("--output-format") + 1] == "stream-json"
        assert "--verbose" in cmd
        assert "do thing" in cmd[-1]  # prompt stays the final positional arg


class TestSessionTimeoutClamp:
    def test_clamps_to_remaining_wall_clock_budget(self, loop_module):
        """C15: a near-exhausted wall-clock budget shrinks the session timeout
        far below the full timeout_build (default 4 h)."""
        import time
        now = time.monotonic()
        args = _args(timeout_build=4 * 3600.0, wall_clock_deadline=now + 5.0)
        clamped = loop_module._session_timeout(args, now)
        assert clamped <= 5.0
        assert clamped < 4 * 3600.0

    def test_no_deadline_returns_full_timeout(self, loop_module):
        import time
        args = _args(timeout_build=4 * 3600.0)  # no wall_clock_deadline attr
        assert loop_module._session_timeout(args, time.monotonic()) == 4 * 3600.0

    def test_past_deadline_floors_at_one_second(self, loop_module):
        import time
        now = time.monotonic()
        args = _args(timeout_build=4 * 3600.0, wall_clock_deadline=now - 100.0)
        assert loop_module._session_timeout(args, now) == 1.0


class TestTimerRace:
    def test_timeout_callback_noop_when_proc_already_exited(self, loop_module, tmp_path):
        """C16: the Timer fires after the process exits cleanly; it must NOT
        flip the hit-timeout flag (which would mislabel a clean run as rc=124).

        Deterministic: a tiny per-line sleep keeps the drain loop alive long
        enough for the 0-delay timer to fire mid-stream, while the proc reports
        itself already exited (poll() is not None) the whole time.
        """
        import time
        log_path = tmp_path / "race.log"

        def _slow_lines():
            for line in ("a\n", "b\n"):
                time.sleep(0.05)
                yield line

        class _ExitedProc:
            returncode = 0
            stdout = _slow_lines()

            def poll(self) -> int:
                return 0  # already exited

            def wait(self, timeout: float | None = None) -> int:
                return 0

            def terminate(self) -> None:
                raise AssertionError("terminate must not be called on an exited proc")

        proc = _ExitedProc()
        with open(log_path, "w") as lf:
            timed_out = loop_module._timed_stream(proc, lf, 0.0)
        assert timed_out is False


class TestTokenEstimateFallback:
    def test_unparseable_session_increments_tokens_by_estimate(self, loop_module, state_dir):
        """C14: a session with no parseable usage must substitute the per-iter
        TOKEN estimate (not leave tokens at 0), so --max-tokens can still trip."""
        import _budget
        _write_state(state_dir, {"status": "running", "current_phase": 1, "total_phases": 3})
        with patch.object(loop_module, "run_claude_session", return_value=0), \
             patch.object(loop_module, "git_head", return_value="cafe"), \
             patch.object(_budget, "count_claude_pids", return_value=0), \
             patch.object(_budget, "parse_session_usage", return_value=(0.0, 0)):
            loop_module.loop_iteration(
                1, _args(per_iter_cost_estimate=0.25, per_iter_token_estimate=12_345)
            )
        state = json.loads((state_dir / "state.json").read_text())
        assert state["tokens"] == 12_345
        rec = json.loads((loop_module.LOG_DIR / "usage.jsonl").read_text().splitlines()[0])
        assert rec["tokens"] == 12_345 and rec["source"] == "estimate"

    def test_zero_cost_nonzero_tokens_preserved(self, loop_module, state_dir):
        """C15 (regression pin for #60): subscription/Max plans report cost=0 but real
        token usage.  parse_session_usage → (0.0, 5000) must accumulate 5000 tokens,
        NOT the flat per_iter_token_estimate.  The old code unconditionally overwrote
        log_tokens with the estimate whenever log_cost <= 0."""
        import _budget
        _write_state(state_dir, {"status": "running", "current_phase": 1, "total_phases": 3})
        with patch.object(loop_module, "run_claude_session", return_value=0), \
             patch.object(loop_module, "git_head", return_value="cafe"), \
             patch.object(_budget, "count_claude_pids", return_value=0), \
             patch.object(_budget, "parse_session_usage", return_value=(0.0, 5000)):
            loop_module.loop_iteration(
                1, _args(per_iter_cost_estimate=0.25, per_iter_token_estimate=100_000)
            )
        state = json.loads((state_dir / "state.json").read_text())
        assert state["tokens"] == 5000, (
            f"expected 5000 (parsed), got {state['tokens']} (flat estimate leaked in)"
        )
        rec = json.loads((loop_module.LOG_DIR / "usage.jsonl").read_text().splitlines()[0])
        assert rec["tokens"] == 5000
