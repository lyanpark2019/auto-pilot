from __future__ import annotations
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _config  # noqa: E402


def test_load_returns_config():
    cfg = _config.load()
    assert isinstance(cfg, _config.AutoPilotConfig)
    assert cfg.claude_bin
    assert cfg.default_max_iter == 100
    assert cfg.default_sleep_sec == 10
    assert cfg.default_timeout_build_sec == 4 * 3600
    assert 8000 in cfg.monitored_ports


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
