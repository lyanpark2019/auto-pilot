from __future__ import annotations

import json
import re

from scripts import _log
from scripts._log import event


def test_event_redacts_secret_like_fields(capsys) -> None:
    _log._RUN_ID = None
    event(
        "sample.secret",
        api_key="sk-live",
        token="tok-live",
        password="pw-live",
        safe="visible",
    )

    captured = capsys.readouterr()

    assert "api_key=<redacted>" in captured.err
    assert "token=<redacted>" in captured.err
    assert "password=<redacted>" in captured.err
    assert "safe=visible" in captured.err
    assert "sk-live" not in captured.err
    assert "tok-live" not in captured.err
    assert "pw-live" not in captured.err


def test_event_redacts_secret_like_values(capsys) -> None:
    _log._RUN_ID = None
    event("sample.value", message="Bearer abcdefghijklmnop", url="https://example.test")

    captured = capsys.readouterr()

    assert "message=<redacted>" in captured.err
    assert "Bearer abcdefghijklmnop" not in captured.err
    assert "url=https://example.test" in captured.err


def test_event_redacts_gh_token_values(capsys) -> None:
    _log._RUN_ID = None
    event("sample.gh", note="ghp_abcdefghijklmnop", plain="ok")

    captured = capsys.readouterr()

    assert "note=<redacted>" in captured.err
    assert "ghp_abcdefghijklmnop" not in captured.err
    assert "plain=ok" in captured.err


def test_event_redacts_authorization_key(capsys) -> None:
    _log._RUN_ID = None
    event("sample.auth", authorization="Basic dXNlcjpwYXNz", visible="yes")

    captured = capsys.readouterr()

    assert "authorization=<redacted>" in captured.err
    assert "dXNlcjpwYXNz" not in captured.err
    assert "visible=yes" in captured.err


def test_log_event_emits_to_stderr_a(capsys) -> None:
    _log._RUN_ID = None
    event("smoke.a", k="v")
    assert "smoke.a" in capsys.readouterr().err


def test_log_event_emits_to_stderr_b(capsys) -> None:
    _log._RUN_ID = None
    event("smoke.b", k="v")
    assert "smoke.b" in capsys.readouterr().err


# ── New tests: timestamp + run_id prefix ─────────────────────────────────────


def test_event_line_has_iso_timestamp_prefix(
    capsys, monkeypatch, tmp_path
) -> None:
    _log._RUN_ID = None
    monkeypatch.delenv("AUTO_PILOT_RUN_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    event("x")
    err = capsys.readouterr().err
    assert re.match(r"^ts=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00 run_id=", err)


def test_event_line_carries_env_run_id(capsys, monkeypatch) -> None:
    _log._RUN_ID = None
    monkeypatch.setenv("AUTO_PILOT_RUN_ID", "rENV")
    event("x")
    err = capsys.readouterr().err
    assert "run_id=rENV " in err
    assert "event=x" in err


def test_event_run_id_falls_back_empty_when_no_state(
    capsys, monkeypatch, tmp_path
) -> None:
    _log._RUN_ID = None
    monkeypatch.delenv("AUTO_PILOT_RUN_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    event("x")
    err = capsys.readouterr().err
    assert "run_id= event=x" in err


def test_event_run_id_read_from_state_json(
    capsys, monkeypatch, tmp_path
) -> None:
    _log._RUN_ID = None
    monkeypatch.delenv("AUTO_PILOT_RUN_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / ".planning" / "auto-pilot"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(json.dumps({"run_id": "rFILE"}))
    event("x")
    err = capsys.readouterr().err
    assert "run_id=rFILE " in err


def test_existing_redaction_unaffected_by_prefix(
    capsys, monkeypatch, tmp_path
) -> None:
    _log._RUN_ID = None
    monkeypatch.delenv("AUTO_PILOT_RUN_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    event("s", api_key="sk-live", safe="ok")
    err = capsys.readouterr().err
    assert "api_key=<redacted>" in err
    assert "safe=ok" in err
    assert err.startswith("ts=")
