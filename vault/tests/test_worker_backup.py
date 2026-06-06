"""Tests for WorkerBackup: snapshot/rollback/purge."""
from __future__ import annotations

import json
from pathlib import Path

from worker_backup import WorkerBackup


def test_snapshot_and_rollback(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    f = vault / "page.md"
    f.write_text("original")

    bak = WorkerBackup(vault, "vault-edge-curator", round_num=1, ticket_id="T1")
    bak.snapshot(f)
    f.write_text("modified")
    assert f.read_text() == "modified"

    bak.rollback()
    assert f.read_text() == "original"


def test_commit_keeps_backup(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    f = vault / "page.md"
    f.write_text("v1")

    bak = WorkerBackup(vault, "w", round_num=1, ticket_id="T1")
    bak.snapshot(f)
    f.write_text("v2")
    bak.commit()

    backups = list(vault.glob("*.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == "v1"


def test_rollback_ticket_classmethod(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    f1 = vault / "a.md"
    f2 = vault / "b.md"
    f1.write_text("a-orig")
    f2.write_text("b-orig")

    bak = WorkerBackup(vault, "w", round_num=2, ticket_id="T42")
    bak.snapshot_many([f1, f2])
    f1.write_text("a-mod")
    f2.write_text("b-mod")
    bak.commit()

    result = WorkerBackup.rollback_ticket(vault, "T42")
    assert result["rolled_back"] == 2
    assert f1.read_text() == "a-orig"
    assert f2.read_text() == "b-orig"


def test_purge_keeps_recent_rounds(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    f = vault / "page.md"
    f.write_text("x")

    for r in (1, 2, 3, 4):
        b = WorkerBackup(vault, "w", round_num=r, ticket_id=f"T{r}")
        b.snapshot(f)
        b.commit()

    purged = WorkerBackup.purge_older_than_rounds(vault, keep_rounds=2)
    assert purged == 2
    remaining = sorted(vault.glob("*.bak.*"))
    assert len(remaining) == 2


def test_audit_log_appended(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    f = vault / "page.md"
    f.write_text("x")

    b = WorkerBackup(vault, "w", round_num=1, ticket_id="T1")
    b.snapshot(f)
    b.commit()

    index = vault / "meta" / ".backups.jsonl"
    assert index.exists()
    lines = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    ops = [ln["op"] for ln in lines]
    assert "snapshot" in ops
    assert "commit" in ops
