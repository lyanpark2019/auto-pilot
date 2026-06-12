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


# Full leak list from the 2026-06-10 cold security re-audit. Under the old
# name-denylist + regex these reached the `claude -p` reviewer subprocess.
# The default-deny allowlist must drop EVERY one of them.
_LEAK_VARS = [
    "STRIPE_SK",
    "SK_LIVE",
    "PAT",
    "GH_PAT",
    "GITLAB_PAT",
    "NPM_AUTH",
    "APIKEY",
    "ACCESS_KEY_ID",
    "AWS_ACCESS_KEY_ID",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "SENTRY_DSN",
    "TWILIO_AUTH",
    "JWT",
    "BEARER",
    "SESSION_COOKIE",
    "CREDENTIALS",
    "VAULT_ADDR",
    "KUBECONFIG",
    "MONGODB_URI",
    "MONGO_URL",
    "RABBITMQ_URL",
    "AMQP_URL",
    "BASIC_AUTH",
    "HTPASSWD",
    "MYSQL_PASSWORD",
    # vars the regex-floor caught before — must still be absent under allowlist
    "GH_CLIENT_ID",
    "GH_CLIENT_SECRET",
    "GH_TOKEN",
    "MY_API_TOKEN",
    "DB_PASSWORD",
    "SOME_SECRET",
    "STRIPE_KEY",
    "GITHUB_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "ANTHROPIC_API_KEY",
]


@pytest.mark.parametrize("secret", _LEAK_VARS)
def test_reviewer_env_strips_secrets(monkeypatch, tmp_path, secret):
    """Each known leak var must be ABSENT from the reviewer env (leak closed)."""
    import _reviewer_wrapper as rw

    monkeypatch.setenv(secret, "SENTINEL_LEAK_VALUE")

    env = rw._reviewer_env("codex-reviewer", tmp_path)

    assert secret not in env, f"{secret} leaked to reviewer env"
    assert env["AUTO_PILOT_SUBAGENT_ROLE"] == "codex-reviewer"


def test_reviewer_env_forwards_operational_vars(monkeypatch, tmp_path):
    """Operational vars a CLI subprocess needs must SURVIVE the allowlist."""
    import _reviewer_wrapper as rw

    survivors = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/Users/test",
        "LANG": "en_US.UTF-8",
        "TMPDIR": "/tmp",
        "LC_ALL": "C.UTF-8",          # LC_ prefix
        "CLAUDE_CONFIG_DIR": "/home/test/.claude",  # CLAUDE_ prefix
        "CLAUDECODE": "1",            # runtime marker
        "XDG_CONFIG_HOME": "/home/test/.config",    # XDG_ prefix
    }
    for k, v in survivors.items():
        monkeypatch.setenv(k, v)

    env = rw._reviewer_env("codex-reviewer", tmp_path)

    for k, v in survivors.items():
        assert env.get(k) == v, f"{k} must survive the allowlist"


@pytest.mark.parametrize("app_var", ["MY_APP_FEATURE_FLAG", "DATABASE_HOST"])
def test_reviewer_env_drops_unknown_app_vars(monkeypatch, tmp_path, app_var):
    """Default-deny: a benign-but-unknown app var is dropped, not just secrets."""
    import _reviewer_wrapper as rw

    monkeypatch.setenv(app_var, "value")

    env = rw._reviewer_env("codex-reviewer", tmp_path)

    assert app_var not in env, f"{app_var} should be dropped by default-deny"


def test_reviewer_env_sets_subagent_role_and_output_dir(monkeypatch, tmp_path):
    """AUTO_PILOT_SUBAGENT_ROLE / AUTO_PILOT_OUTPUT_DIR are always set."""
    import _reviewer_wrapper as rw

    env = rw._reviewer_env("claude-reviewer", tmp_path / "out")

    assert env["AUTO_PILOT_SUBAGENT_ROLE"] == "claude-reviewer"
    assert env["AUTO_PILOT_OUTPUT_DIR"] == str(tmp_path / "out")


@pytest.fixture()
def restore_rw_module():
    """Reload _reviewer_wrapper AFTER monkeypatch teardown restores _routing.

    Ordering: list this fixture BEFORE monkeypatch in the test signature.
    Pytest finalizes fixtures in reverse setup order, so this fixture tears
    down LAST — its reload therefore runs after monkeypatch has restored
    _routing.codex_timeouts to the real function.

    The post-reload assertion inside this fixture confirms the trap is closed:
    HARD_KILL_SEC must match the value derived from the live routing config.
    """
    import importlib
    import _reviewer_wrapper as rw
    import _routing

    yield

    # monkeypatch has already restored _routing.codex_timeouts by now.
    importlib.reload(rw)
    try:
        _t, _r = _routing.codex_timeouts()
        expected = max(480, _t + _r + 120)
    except Exception:
        expected = 480
    assert rw.HARD_KILL_SEC == expected, (
        f"after reload HARD_KILL_SEC={rw.HARD_KILL_SEC}, expected {expected} "
        f"(derived from live routing config — ordering trap not closed)"
    )


def test_hard_kill_derived_from_routing(restore_rw_module, monkeypatch):
    """HARD_KILL_SEC must be >= sum(codex_timeouts()) + 120 when routing is available."""
    import importlib
    import _reviewer_wrapper as rw
    import _routing

    # Monkeypatch _routing.codex_timeouts to return (240, 180); expected floor = 540.
    monkeypatch.setattr(_routing, "codex_timeouts", lambda config=None: (240, 180))

    # Force re-import to pick up the monkeypatched value.
    importlib.reload(rw)
    assert rw.HARD_KILL_SEC >= 540, (
        f"HARD_KILL_SEC={rw.HARD_KILL_SEC} < 540 (240+180+120)"
    )


def test_hard_kill_fallback_on_routing_error(restore_rw_module, monkeypatch):
    """RoutingConfigError during import must fall back to static 480 s."""
    import importlib
    import _reviewer_wrapper as rw
    import _routing

    monkeypatch.setattr(_routing, "codex_timeouts",
                        lambda config=None: (_ for _ in ()).throw(
                            _routing.RoutingConfigError("yaml missing")))

    importlib.reload(rw)
    assert rw.HARD_KILL_SEC == 480, (
        f"Expected fallback 480, got {rw.HARD_KILL_SEC}"
    )


def test_reviewer_cmd_uses_equals_form_so_prompt_not_swallowed(tmp_path):
    """--allowedTools and --disallowedTools must use equals-form single tokens.

    claude CLI >=2.1.175 treats --disallowedTools as variadic: space-form
    causes the following positional (the prompt) to be consumed as an extra
    disallowed-tool name, producing a promptless reviewer session.
    """
    import _reviewer_wrapper as rw

    ticket = tmp_path / "contract.json"
    allowed = "Read,Bash,Write"
    disallowed = "WebFetch,Agent"

    cmd = rw._reviewer_cmd(ticket, allowed, disallowed)

    # 1. Both flags must be single equals-form tokens.
    assert f"--allowedTools={allowed}" in cmd, (
        f"expected equals-form --allowedTools={allowed!r} in {cmd}"
    )
    assert f"--disallowedTools={disallowed}" in cmd, (
        f"expected equals-form --disallowedTools={disallowed!r} in {cmd}"
    )

    # 2. No bare (space-form) flag token — that is the variadic-swallow bug.
    assert "--allowedTools" not in cmd, (
        "bare --allowedTools found; space-form is the variadic bug"
    )
    assert "--disallowedTools" not in cmd, (
        "bare --disallowedTools found; space-form is the variadic bug"
    )

    # 3. The prompt is the last element and is a distinct token (not embedded
    #    inside a flag value).
    last = cmd[-1]
    assert f"TICKET={ticket}" in last, (
        f"prompt must be last element containing TICKET=<path>; got {last!r}"
    )
    assert last.startswith("--") is False, (
        "last element must be the prompt positional, not a flag"
    )
