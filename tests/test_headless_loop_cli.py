"""Additional headless-loop CLI and subprocess coverage tests."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent


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
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _write_state(state_dir: Path, status: str = "running", current_phase: int = 1) -> None:
    (state_dir / "state.json").write_text(
        json.dumps({"status": status, "current_phase": current_phase, "total_phases": 3})
    )


@pytest.mark.parametrize(("iter_n", "phase"), [(1, 1), (9, 4)])
def test_commit_trailer_records_iteration_and_phase(loop_module, iter_n: int, phase: int) -> None:
    trailer = loop_module.commit_trailer(iter_n, phase)

    assert f"auto-pilot-iter: {iter_n}" in trailer
    assert f"auto-pilot-phase: {phase}" in trailer


def test_git_head_returns_current_sha(loop_module, tmp_path) -> None:
    import subprocess as sp

    sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    sp.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    expected = sp.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()

    with patch.object(loop_module, "ROOT", tmp_path):
        assert loop_module.git_head() == expected


@pytest.mark.parametrize("step", ["status", "push"])
def test_stash_timeout_paths_degrade_to_none(loop_module, step: str) -> None:
    timeout = subprocess.TimeoutExpired(["git"], 30)

    if step == "status":
        with patch.object(loop_module.subprocess, "run", side_effect=timeout):
            assert loop_module.stash_if_dirty("timeout") is None
        return

    status = MagicMock(returncode=0, stdout=" M file.py\n", stderr="")
    with patch.object(loop_module.subprocess, "run", side_effect=[status, timeout]):
        assert loop_module.stash_if_dirty("timeout") is None


def test_stash_push_failure_degrades_to_none(loop_module) -> None:
    status = MagicMock(returncode=0, stdout=" M file.py\n", stderr="")
    failed = MagicMock(returncode=1, stdout="", stderr="cannot stash")

    with patch.object(loop_module.subprocess, "run", side_effect=[status, failed]):
        assert loop_module.stash_if_dirty("fail") is None


def test_timed_stream_copies_stdout_to_log(loop_module, tmp_path, capsys) -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", "print('hello from child')"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log = tmp_path / "session.log"

    with log.open("w") as lf:
        timed_out = loop_module._timed_stream(proc, lf, 5)

    assert timed_out is False
    assert "hello from child" in log.read_text()
    assert "hello from child" in capsys.readouterr().out


def test_timed_stream_kills_on_timeout(loop_module, tmp_path) -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; print('start', flush=True); time.sleep(5)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log = tmp_path / "session.log"

    with log.open("w") as lf:
        timed_out = loop_module._timed_stream(proc, lf, 0.1)

    assert timed_out is True
    assert "[TIMEOUT]" in log.read_text()


def test_run_claude_session_streams_and_returns_code(loop_module, tmp_path) -> None:
    class FakeProc:
        stdout = iter(["ok\n"])
        returncode = 7

        def wait(self, timeout=None):
            return self.returncode

        def terminate(self):
            raise AssertionError("terminate should not be called")

        def kill(self):
            raise AssertionError("kill should not be called")

    fake = FakeProc()
    log = tmp_path / "claude.log"

    with patch.object(loop_module.subprocess, "Popen", return_value=fake) as popen:
        rc = loop_module.run_claude_session("prompt", log, 3)

    assert rc == 7
    assert log.read_text() == "ok\n"
    kwargs = popen.call_args.kwargs
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["env"]["HARNESS_HEADLESS"] == "1"


def test_run_claude_session_timeout_returns_124(loop_module, tmp_path) -> None:
    fake = MagicMock(returncode=0, stdout=iter([]))
    with patch.object(loop_module.subprocess, "Popen", return_value=fake), \
         patch.object(loop_module, "_timed_stream", return_value=True):
        assert loop_module.run_claude_session("prompt", tmp_path / "timeout.log", 3) == 124


@pytest.mark.parametrize(
    ("status", "expected_rc"),
    [("success", 0), ("failed", 1), ("pivot-needed", 1), ("cost-cap", 1)],
)
def test_main_terminal_status_codes(loop_module, state_dir, status: str, expected_rc: int) -> None:
    _write_state(state_dir, status="running")

    with patch.object(loop_module, "loop_iteration", return_value=status):
        assert loop_module.main(["--max-iter", "3", "--sleep", "0"]) == expected_rc


def test_main_no_state_file_returns_2(loop_module) -> None:
    assert loop_module.main(["--once"]) == 2


def test_main_once_exits_zero_after_nonterminal_iteration(loop_module, state_dir) -> None:
    _write_state(state_dir, status="running")

    with patch.object(loop_module, "loop_iteration", return_value="running"):
        assert loop_module.main(["--once", "--sleep", "0"]) == 0


def test_main_max_iter_exhaustion_returns_zero(loop_module, state_dir) -> None:
    _write_state(state_dir, status="running")

    with patch.object(loop_module, "loop_iteration", return_value="running") as iteration:
        assert loop_module.main(["--max-iter", "2", "--sleep", "0"]) == 0

    assert iteration.call_count == 2
