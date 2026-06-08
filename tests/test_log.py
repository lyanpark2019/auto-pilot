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
