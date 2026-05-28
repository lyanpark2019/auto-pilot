"""Tests for scripts/_worktree.py."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _worktree  # noqa: E402


def test_worktree_handle_serialization(tmp_path):
    h = _worktree.WorktreeHandle(
        path=tmp_path / "wt",
        branch="auto-pilot/iter-1/phase-1/contract-1/round-1",
        base_sha="abcdef1234567890abcdef1234567890abcdef12",
        contract_id="iter-1/phase-1/contract-1/round-1",
        created_at="2026-05-28T10:00:00+00:00",
    )
    target = tmp_path / "handle.json"
    h.write(target)
    assert target.exists()
    h2 = _worktree.WorktreeHandle.read(target)
    assert h2 == h


def test_patch_result_variants():
    assert isinstance(_worktree.NoOp(), _worktree.PatchResult)
    assert isinstance(_worktree.NeedsRebase(reason="x", current_base="y"), _worktree.PatchResult)
    assert isinstance(_worktree.RejectMultipleCommits(count=3), _worktree.PatchResult)
    p = Path("/tmp/series.mbox")
    assert isinstance(_worktree.PatchSeries(mbox=p), _worktree.PatchResult)
