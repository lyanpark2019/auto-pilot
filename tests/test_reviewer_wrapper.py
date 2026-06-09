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
        def __init__(self, out, role="test"):
            self.output_dir = out
            self.role = role
            self._spawn_kwargs: dict = {}
        def poll(self): return 0

    handles = [FakeHandle(h1_out, "r1"), FakeHandle(h2_out, "r2")]
    (h1_out / "done.marker").touch()
    (h2_out / "done.marker").touch()

    failures = rw.wait_all(handles, timeout_sec=2)
    assert failures == []


def test_spawn_redacts_denylist_secrets(monkeypatch, tmp_path):
    """Spawned subprocess env must not contain denylist entries."""
    import _reviewer_wrapper as rw

    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SENTINEL_SECRET_VALUE")
    monkeypatch.setenv("GITHUB_TOKEN", "gh_SENTINEL")

    captured_env: dict = {}

    def fake_popen(cmd, env, **kwargs):
        captured_env.update(env)
        class P:
            def poll(self): return 0
            def terminate(self): pass
        return P()

    monkeypatch.setattr(rw.subprocess, "Popen", fake_popen)

    rw.spawn(role="codex-reviewer", ticket=tmp_path / "t.json",
             output_dir=tmp_path / "o", allowed_tools="Read",
             disallowed_tools="WebFetch")

    assert "AWS_SECRET_ACCESS_KEY" not in captured_env, "denylist secret leaked into subprocess env"
    assert "GITHUB_TOKEN" not in captured_env, "denylist secret leaked into subprocess env"
    assert captured_env.get("AUTO_PILOT_SUBAGENT_ROLE") == "codex-reviewer"


def test_wait_all_times_out(tmp_path):
    import _reviewer_wrapper as rw

    class FakeHandle:
        def __init__(self, out, role="test"):
            self.output_dir = out
            self.role = role
            self._spawn_kwargs: dict = {}
        def poll(self): return None

    handle = FakeHandle(tmp_path, "r1")
    with pytest.raises(rw.SpawnTimeoutError):
        rw.wait_all([handle], timeout_sec=1)


def test_reviewer_env_strips_secrets(monkeypatch, tmp_path):
    """_reviewer_env must not forward secret vars to subprocess env."""
    import _reviewer_wrapper as rw

    secret_vars = [
        "GH_CLIENT_ID",
        "GH_CLIENT_SECRET",
        "GH_TOKEN",
        "MY_API_TOKEN",
        "DB_PASSWORD",
        "SOME_SECRET",
        "STRIPE_KEY",
        "GITHUB_TOKEN",
    ]
    for k in secret_vars:
        monkeypatch.setenv(k, "leak")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = rw._reviewer_env("codex-reviewer", tmp_path)

    for k in secret_vars:
        assert k not in env, f"{k} leaked to reviewer env"
    assert env["PATH"] == "/usr/bin"
    assert env["AUTO_PILOT_SUBAGENT_ROLE"] == "codex-reviewer"
