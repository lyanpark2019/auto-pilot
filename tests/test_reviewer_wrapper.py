"""Tests for scripts/_reviewer_wrapper.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def test_spawn_uses_isolated_env(monkeypatch, tmp_path):
    """Each spawn must get its own env dict; parent env must not be mutated."""
    import _reviewer_wrapper as rw
    monkeypatch.delenv("AUTO_PILOT_SUBAGENT_ROLE", raising=False)
    monkeypatch.delenv("AUTO_PILOT_OUTPUT_DIR", raising=False)

    captured_envs = []

    def fake_popen(cmd, env, **kwargs):
        captured_envs.append(env)
        class P:
            def __init__(self): self.returncode = 0
            def wait(self): return 0
            def poll(self): return 0
            def terminate(self): pass
        return P()

    monkeypatch.setattr(rw.subprocess, "Popen", fake_popen)

    rw.spawn(role="codex-reviewer", ticket=tmp_path / "t1.json",
             output_dir=tmp_path / "o1", allowed_tools="Read,Bash",
             disallowed_tools="WebFetch")
    rw.spawn(role="claude-reviewer", ticket=tmp_path / "t2.json",
             output_dir=tmp_path / "o2", allowed_tools="Read,Bash",
             disallowed_tools="WebFetch")

    assert captured_envs[0]["AUTO_PILOT_SUBAGENT_ROLE"] == "codex-reviewer"
    assert captured_envs[1]["AUTO_PILOT_SUBAGENT_ROLE"] == "claude-reviewer"
    assert captured_envs[0]["AUTO_PILOT_OUTPUT_DIR"] == str(tmp_path / "o1")
    assert captured_envs[1]["AUTO_PILOT_OUTPUT_DIR"] == str(tmp_path / "o2")
    import os
    assert "AUTO_PILOT_SUBAGENT_ROLE" not in os.environ


def test_wait_all_returns_when_all_done_markers_appear(monkeypatch, tmp_path):
    import _reviewer_wrapper as rw

    h1_out = tmp_path / "o1"
    h1_out.mkdir()
    h2_out = tmp_path / "o2"
    h2_out.mkdir()

    class FakeHandle:
        def __init__(self, out): self.output_dir = out
        def poll(self): return 0

    handles = [FakeHandle(h1_out), FakeHandle(h2_out)]
    (h1_out / "done.marker").touch()
    (h2_out / "done.marker").touch()

    rw.wait_all(handles, timeout_sec=2)


def test_wait_all_times_out(tmp_path):
    import _reviewer_wrapper as rw

    class FakeHandle:
        def __init__(self, out): self.output_dir = out
        def poll(self): return None

    handle = FakeHandle(tmp_path)
    with pytest.raises(rw.SpawnTimeoutError):
        rw.wait_all([handle], timeout_sec=1)
