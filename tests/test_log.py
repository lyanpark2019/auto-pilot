from __future__ import annotations

from scripts._log import event


def test_event_redacts_secret_like_fields(capsys) -> None:
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
    event("sample.value", message="Bearer abcdefghijklmnop", url="https://example.test")

    captured = capsys.readouterr()

    assert "message=<redacted>" in captured.err
    assert "Bearer abcdefghijklmnop" not in captured.err
    assert "url=https://example.test" in captured.err


def test_event_redacts_gh_token_values(capsys) -> None:
    event("sample.gh", note="ghp_abcdefghijklmnop", plain="ok")

    captured = capsys.readouterr()

    assert "note=<redacted>" in captured.err
    assert "ghp_abcdefghijklmnop" not in captured.err
    assert "plain=ok" in captured.err


def test_event_redacts_authorization_key(capsys) -> None:
    event("sample.auth", authorization="Basic dXNlcjpwYXNz", visible="yes")

    captured = capsys.readouterr()

    assert "authorization=<redacted>" in captured.err
    assert "dXNlcjpwYXNz" not in captured.err
    assert "visible=yes" in captured.err


def test_log_event_emits_to_stderr_a(capsys) -> None:
    event("smoke.a", k="v")
    assert "smoke.a" in capsys.readouterr().err
