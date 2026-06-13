from __future__ import annotations
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CONFIG_DOC = REPO / "docs" / "configuration.md"
sys.path.insert(0, str(REPO / "scripts"))

import _config  # noqa: E402


def test_load_returns_config():
    cfg = _config.load()
    assert isinstance(cfg, _config.AutoPilotConfig)
    assert cfg.claude_bin
    assert cfg.default_max_iter == 100
    assert cfg.default_sleep_sec == 10
    assert cfg.default_timeout_build_sec == 4 * 3600


def test_claude_bin_env_override(monkeypatch):
    monkeypatch.setenv("CLAUDE_BIN", "/custom/claude")
    cfg = _config.load()
    assert cfg.claude_bin == "/custom/claude"


def test_headless_env_complete():
    cfg = _config.load()
    assert cfg.headless_env == {
        "HARNESS_HEADLESS": "1",
        "AUTO_PILOT_HEADLESS": "1",
    }


# ---------------------------------------------------------------------------
# Validation: valid defaults pass __post_init__
# ---------------------------------------------------------------------------

def test_valid_defaults_pass_validation():
    cfg = _config.AutoPilotConfig(claude_bin="claude")
    assert cfg.default_max_iter == 100
    assert cfg.preflight_ttl_sec == 900


def test_valid_custom_values_pass_validation():
    cfg = _config.AutoPilotConfig(
        claude_bin="claude",
        default_max_iter=1,
        default_sleep_sec=1,
        default_timeout_build_sec=1.0,
        default_max_cost_usd=0.01,
        default_max_tokens=1,
        default_per_iter_cost_estimate_usd=0.01,
        default_max_concurrent_claude=1,
        preflight_ttl_sec=60,
    )
    assert cfg.default_max_iter == 1


# ---------------------------------------------------------------------------
# Validation: each invalid field raises ValueError naming the field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,kwargs", [
    ("default_max_iter",               {"default_max_iter": 0}),
    ("default_max_iter",               {"default_max_iter": 10_001}),
    ("default_sleep_sec",              {"default_sleep_sec": 0}),
    ("default_sleep_sec",              {"default_sleep_sec": 3_601}),
    ("default_timeout_build_sec",      {"default_timeout_build_sec": 0.0}),
    ("default_timeout_build_sec",      {"default_timeout_build_sec": 86_401.0}),
    ("default_max_cost_usd",           {"default_max_cost_usd": 0.0}),
    ("default_max_cost_usd",           {"default_max_cost_usd": 10_001.0}),
    ("default_max_tokens",             {"default_max_tokens": 0}),
    ("default_max_tokens",             {"default_max_tokens": 1_000_000_001}),
    ("default_per_iter_cost_estimate_usd", {"default_per_iter_cost_estimate_usd": 0.0}),
    ("default_per_iter_cost_estimate_usd", {"default_per_iter_cost_estimate_usd": 1_001.0}),
    ("default_max_concurrent_claude",  {"default_max_concurrent_claude": 0}),
    ("default_max_concurrent_claude",  {"default_max_concurrent_claude": 65}),
    ("preflight_ttl_sec",              {"preflight_ttl_sec": 59}),
    ("preflight_ttl_sec",              {"preflight_ttl_sec": 86_401}),
])
def test_invalid_field_raises_value_error(field: str, kwargs: dict):
    with pytest.raises(ValueError, match=field):
        _config.AutoPilotConfig(claude_bin="claude", **kwargs)


# ---------------------------------------------------------------------------
# TTL env override
# ---------------------------------------------------------------------------

def test_preflight_ttl_env_override(monkeypatch):
    monkeypatch.setenv("AUTO_PILOT_PREFLIGHT_TTL_SEC", "1800")
    cfg = _config.load()
    assert cfg.preflight_ttl_sec == 1800


def test_preflight_ttl_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("AUTO_PILOT_PREFLIGHT_TTL_SEC", raising=False)
    cfg = _config.load()
    assert cfg.preflight_ttl_sec == 900


def test_preflight_ttl_accessor_env_override(monkeypatch):
    monkeypatch.setenv("AUTO_PILOT_PREFLIGHT_TTL_SEC", "1200")
    assert _config.preflight_ttl_sec() == 1200


def test_preflight_ttl_accessor_default_when_unset(monkeypatch):
    monkeypatch.delenv("AUTO_PILOT_PREFLIGHT_TTL_SEC", raising=False)
    assert _config.preflight_ttl_sec() == 900


@pytest.mark.parametrize("raw", ["", "abc", "12.5", "  ", "0x10", "nan"])
def test_preflight_ttl_accessor_garbage_falls_back(monkeypatch, raw):
    monkeypatch.setenv("AUTO_PILOT_PREFLIGHT_TTL_SEC", raw)
    assert _config.preflight_ttl_sec() == 900


@pytest.mark.parametrize("raw,expected", [("59", 900), ("86401", 900), ("60", 60), ("86400", 86400)])
def test_preflight_ttl_accessor_clamps_out_of_range(monkeypatch, raw, expected):
    monkeypatch.setenv("AUTO_PILOT_PREFLIGHT_TTL_SEC", raw)
    assert _config.preflight_ttl_sec() == expected


def test_dispatch_import_survives_garbage_ttl(monkeypatch):
    import importlib
    monkeypatch.setenv("AUTO_PILOT_PREFLIGHT_TTL_SEC", "not-an-int")
    import _dispatch
    importlib.reload(_dispatch)  # must not raise
    monkeypatch.delenv("AUTO_PILOT_PREFLIGHT_TTL_SEC", raising=False)
    importlib.reload(_dispatch)


@pytest.mark.parametrize(
    "token",
    [
        "CLAUDE_BIN",
        "AUTO_PILOT_PREFLIGHT_TTL_SEC",
        "default_max_iter",
        "default_sleep_sec",
        "default_timeout_build_sec",
        "default_max_cost_usd",
        "default_max_tokens",
        "default_per_iter_cost_estimate_usd",
        "default_max_concurrent_claude",
    ],
)
def test_configuration_doc_mentions_public_settings(token: str) -> None:
    text = CONFIG_DOC.read_text(encoding="utf-8")

    assert token in text
