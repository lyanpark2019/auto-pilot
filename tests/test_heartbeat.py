from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _heartbeat  # noqa: E402


def test_write_beat_creates_status_shape(tmp_path):
    out = tmp_path / "outputs" / "codex-reviewer"
    _heartbeat.write_beat(out, "codex-reviewer", "codex-attempt-1:medium",
                          risk_tier="medium")
    data = json.loads((out / "status.json").read_text())
    assert data["role"] == "codex-reviewer"
    assert data["phase"] == "codex-attempt-1:medium"
    assert data["risk_tier"] == "medium"
    assert data["elapsed_s"] >= 0
    assert data["started_at"] and data["last_beat"]


def test_second_beat_preserves_started_at(tmp_path):
    out = tmp_path / "outputs" / "codex-reviewer"
    _heartbeat.write_beat(out, "codex-reviewer", "start", risk_tier="low")
    first = json.loads((out / "status.json").read_text())
    _heartbeat.write_beat(out, "codex-reviewer", "codex-retry:low", risk_tier="low")
    second = json.loads((out / "status.json").read_text())
    assert second["started_at"] == first["started_at"]
    assert second["phase"] == "codex-retry:low"


def test_write_beat_survives_corrupt_existing_file(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "status.json").write_text("{ not json")
    _heartbeat.write_beat(out, "claude-reviewer", "review-start")
    assert json.loads((out / "status.json").read_text())["role"] == "claude-reviewer"


def _fabricate_round(root: Path, rel: str, roles: list[str]) -> None:
    rdir = root / rel
    for role in roles:
        out = rdir / "outputs" / role
        out.mkdir(parents=True)
        _heartbeat.write_beat(out, role, "review-start", risk_tier="medium")


def test_render_table_lists_active_round_roles(tmp_path):
    root = tmp_path / "contracts"
    _fabricate_round(root, "iter-1/phase-1/contract-1/round-1",
                     ["codex-reviewer", "claude-reviewer"])
    table = _heartbeat.render_table(root)
    assert "codex-reviewer" in table
    assert "claude-reviewer" in table
    assert "review-start" in table


def test_render_table_empty_tree(tmp_path):
    assert "no reviewer status" in _heartbeat.render_table(tmp_path / "contracts")


def test_beat_cli(tmp_path):
    import subprocess
    script = Path(__file__).resolve().parent.parent / "scripts" / "_heartbeat.py"
    out = tmp_path / "o"
    rc = subprocess.run(
        [sys.executable, str(script), "beat", "--out-dir", str(out),
         "--role", "claude-reviewer", "--phase", "review-start",
         "--risk-tier", "high"],
        capture_output=True, text=True)
    assert rc.returncode == 0, rc.stderr
    assert json.loads((out / "status.json").read_text())["risk_tier"] == "high"
