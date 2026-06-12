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


# --- regression: P2 non-dict status.json ---

def test_write_beat_list_shaped_existing_status(tmp_path):
    """P2: existing status.json is a JSON list — write_beat must fresh-start, not crash."""
    out = tmp_path / "o"
    out.mkdir()
    (out / "status.json").write_text("[1, 2, 3]")
    _heartbeat.write_beat(out, "codex-reviewer", "review-start")
    data = json.loads((out / "status.json").read_text())
    assert data["role"] == "codex-reviewer"
    assert data["started_at"]  # fresh started_at written


def test_render_table_skips_list_shaped_status_keeps_valid(tmp_path):
    """P2: round with one list-shaped + one valid status.json — table includes valid role only."""
    root = tmp_path / "contracts"
    round_dir = root / "iter-1/phase-1/contract-1/round-1"
    # valid reviewer
    valid_out = round_dir / "outputs" / "claude-reviewer"
    valid_out.mkdir(parents=True)
    _heartbeat.write_beat(valid_out, "claude-reviewer", "review-start", risk_tier="low")
    # list-shaped reviewer
    bad_out = round_dir / "outputs" / "codex-reviewer"
    bad_out.mkdir(parents=True)
    (bad_out / "status.json").write_text("[1, 2, 3]")
    table = _heartbeat.render_table(root)
    assert "claude-reviewer" in table
    assert "codex-reviewer" not in table


# --- regression: P3 naive (tz-less) timestamps ---

def test_write_beat_naive_started_at_no_crash(tmp_path):
    """P3: existing status.json has naive ISO started_at — write_beat must not raise TypeError."""
    out = tmp_path / "o"
    out.mkdir()
    existing = {
        "role": "claude-reviewer",
        "started_at": "2026-06-12T00:00:00",
        "elapsed_s": 0,
        "last_beat": "2026-06-12T00:00:00",
        "phase": "review-start",
        "risk_tier": None,
    }
    (out / "status.json").write_text(json.dumps(existing))
    # Must not raise; shape must be intact
    _heartbeat.write_beat(out, "claude-reviewer", "review-retry")
    data = json.loads((out / "status.json").read_text())
    assert data["role"] == "claude-reviewer"
    assert data["started_at"]
    assert data["elapsed_s"] >= 0


def test_write_beat_fresh_start_semantics(tmp_path):
    """Carry-in: fresh write_beat — started_at is UTC ISO and elapsed_s is 0."""
    out = tmp_path / "fresh"
    data_written = _heartbeat.write_beat(out, "claude-reviewer", "review-start")
    data = json.loads(data_written.read_text())
    assert data["started_at"].endswith("+00:00"), (
        f"expected UTC offset in started_at, got {data['started_at']!r}"
    )
    assert data["elapsed_s"] == 0


def test_render_table_naive_last_beat_shows_question_mark(tmp_path):
    """P3: status.json with naive last_beat — render_table shows '?' beat-age, no crash."""
    root = tmp_path / "contracts"
    round_dir = root / "iter-1/phase-1/contract-1/round-1"
    out = round_dir / "outputs" / "claude-reviewer"
    out.mkdir(parents=True)
    payload = {
        "role": "claude-reviewer",
        "started_at": "2026-06-12T00:00:00",
        "elapsed_s": 10,
        "last_beat": "2026-06-12T00:00:00",  # naive — no tz
        "phase": "review-start",
        "risk_tier": "low",
    }
    (out / "status.json").write_text(json.dumps(payload))
    table = _heartbeat.render_table(root)
    assert "claude-reviewer" in table
    # Split the data row (second line after header) and assert beat-age column (index 5) is "?"
    lines = [ln for ln in table.splitlines() if "claude-reviewer" in ln]
    assert lines, "expected a data row containing claude-reviewer"
    cols = lines[0].split()
    assert cols[5] == "?", f"expected col[5]=='?' got {cols[5]!r}"
