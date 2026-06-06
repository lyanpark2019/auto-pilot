"""Tests for dashboard_data.collect."""
from __future__ import annotations

import json
from pathlib import Path

import dashboard_data


def test_collect_minimal_vault(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    (vault / "meta").mkdir(parents=True)
    (vault / "meta" / "score-state.json").write_text(json.dumps({"total": 100, "scores": {}}))
    data = dashboard_data.collect(vault)
    assert data["structural"]["total"] == 100
    assert data["content"] is None
    assert data["vault_name"] == "v"


def test_collect_audit_files(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    (vault / "meta").mkdir(parents=True)
    (vault / "meta" / "audit-r1.md").write_text("r1")
    (vault / "meta" / "audit-r2.md").write_text("r2")
    (vault / "meta" / "content-audit-r1.md").write_text("c1")
    data = dashboard_data.collect(vault)
    assert len(data["structural_audits"]) == 2
    assert len(data["content_audits"]) == 1


def test_collect_cost_log(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    cost_dir = vault / "meta" / "_cost"
    cost_dir.mkdir(parents=True)
    (cost_dir / "cost-log.jsonl").write_text(
        json.dumps({"round": 1, "worker": "w", "cost_usd": 1.5}) + "\n"
    )
    data = dashboard_data.collect(vault)
    assert data["cost_log"][0]["worker"] == "w"
