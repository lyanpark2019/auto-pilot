"""Tests for scripts/_recover.py."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _recover  # noqa: E402


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    (repo / ".gitignore").write_text(".planning/\n")
    (repo / "a.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


def _make_terminal_worktree(
    worktree_base: Path,
    state_dir: Path,
    contract_id: str,
    age_hours: float = 48.0,
    status: str = "DONE",
    include_done_marker: bool = True,
) -> Path:
    """Build the sentinel + status files that reap_orphans looks for."""
    wt_path = worktree_base / contract_id
    wt_path.mkdir(parents=True, exist_ok=True)

    sentinel = wt_path / ".auto-pilot-worktree"
    sentinel.write_text(contract_id + "\n")

    now = time.time()
    old_mtime = now - age_hours * 3600
    os.utime(sentinel, (old_mtime, old_mtime))

    outputs = state_dir / "contracts" / contract_id / "outputs" / "worker"
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / "status.json").write_text(json.dumps({"status": status}))
    if include_done_marker:
        (outputs / "done.marker").touch()

    return wt_path


def test_run_recovery_reaps_terminal_aged_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    state_dir = tmp_path / "state"
    worktree_base = state_dir / "worktrees"
    contract_id = "iter-1/phase-1/contract-1/round-1"

    wt_path = _make_terminal_worktree(
        worktree_base, state_dir, contract_id, age_hours=48.0, status="DONE"
    )

    result = _recover.run_recovery(
        repo_root=repo, state_dir=state_dir, max_age_hours=24
    )
    assert str(wt_path) in result["reaped"]


def test_run_recovery_preserves_in_flight(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    state_dir = tmp_path / "state"
    worktree_base = state_dir / "worktrees"
    contract_id = "iter-1/phase-1/contract-1/round-1"

    _make_terminal_worktree(
        worktree_base,
        state_dir,
        contract_id,
        age_hours=48.0,
        status="PARTIAL",
        include_done_marker=False,
    )

    result = _recover.run_recovery(
        repo_root=repo, state_dir=state_dir, max_age_hours=24
    )
    assert result["reaped"] == []


def test_run_recovery_clears_stale_am_after_kill_mid_apply(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    state_dir = tmp_path / "state"

    rebase_apply = repo / ".git" / "rebase-apply"
    rebase_apply.mkdir(parents=True, exist_ok=True)

    result = _recover.run_recovery(repo_root=repo, state_dir=state_dir)
    assert result["stale_am_cleared"] is True
    assert not rebase_apply.exists()


def test_cmd_recover_emits_json_and_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _init_repo(tmp_path)
    state_dir = tmp_path / "state"
    os.chdir(repo)

    ns = argparse.Namespace(max_age_hours=24, state_dir=str(state_dir))
    rc = _recover.cmd_recover(ns)
    assert rc == 0

    out = capsys.readouterr().out
    data = json.loads(out)
    assert "reaped" in data
