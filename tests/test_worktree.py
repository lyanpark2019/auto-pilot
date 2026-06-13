"""Tests for scripts/_worktree.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

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


def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    # .planning/ created by main-apply.lock must not pollute `git status --porcelain`.
    (repo / ".gitignore").write_text(".planning/\n")
    (repo / "a.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


def _fake_contract(repo_root, contract_dir):
    return {
        "id": "iter-1/phase-1/contract-1/round-1",
        "snapshot_shas": {
            "base_sha": subprocess.check_output(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
            ).strip(),
            "spec": "0" * 64,
            "claude_md_chain": [],
        },
    }


def test_create_makes_worktree_with_canonical_branch(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)

    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)

    assert handle.branch == "auto-pilot/iter-1/phase-1/contract-1/round-1"
    assert handle.path.exists()
    sentinel = handle.path / ".auto-pilot-worktree"
    assert sentinel.exists()
    assert sentinel.read_text().strip() == contract["id"]
    persisted = contract_dir / "worktree-handle.json"
    assert persisted.exists()


def test_create_rejects_invalid_branch_name_with_lock_suffix(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    contract["id"] = "iter-1/phase-1/contract-1/round-1.lock"  # invalid

    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    with pytest.raises(_worktree.InvalidBranchNameError):
        mgr.create(contract, contract_dir=contract_dir)


def _commit_one(repo, name, content):
    (repo / name).write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", f"add {name}"], check=True)


def test_collect_patches_returns_noop_on_empty_diff(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    # No commits in worktree → no diff
    result = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(result, _worktree.NoOp)


def test_collect_patches_returns_patch_series_on_single_commit(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "second\n")
    result = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(result, _worktree.PatchSeries)
    assert result.mbox.exists()
    assert result.mbox.read_bytes().startswith(b"From ")


def test_collect_patches_rejects_multiple_commits(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "1\n")
    _commit_one(handle.path, "c.txt", "2\n")
    result = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(result, _worktree.RejectMultipleCommits)
    assert result.count == 2


def test_collect_patches_returns_needs_rebase_when_not_ancestor(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    # Reset worktree HEAD to a different commit not descending from base
    _commit_one(repo, "z.txt", "z\n")  # advance main
    subprocess.run(["git", "-C", str(handle.path), "reset", "--hard", "main"], check=True)
    # Now HEAD does descend, force divergence:
    subprocess.run(["git", "-C", str(handle.path), "checkout", "--orphan", "orphan-branch"], check=True)
    _commit_one(handle.path, "o.txt", "o\n")
    result = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(result, _worktree.NeedsRebase)


def test_apply_to_main_lands_commit_with_trailers(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    contract["idempotency_token"] = "deadbeef00112233"
    contract["iter"] = 1
    contract["phase"] = 1
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "x\n")
    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)

    result = mgr.apply_to_main(series.mbox, contract)
    assert result.status == "applied"

    log = subprocess.check_output(
        ["git", "-C", str(repo), "log", "-1", "--format=%B"],
        text=True,
    )
    assert "auto-pilot-iter: 1" in log
    assert "auto-pilot-phase: 1" in log
    assert "auto-pilot-contract: iter-1/phase-1/contract-1/round-1" in log
    assert "auto-pilot-idempotency: deadbeef00112233" in log


def test_apply_to_main_aborts_on_conflict(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    contract["idempotency_token"] = "cafef00d11223344"
    contract["iter"] = 1
    contract["phase"] = 1
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    # Worker edits a.txt
    (handle.path / "a.txt").write_text("worker-version\n")
    subprocess.run(["git", "-C", str(handle.path), "commit", "-q", "-am", "wt edit"], check=True)
    # Main also edits a.txt (concurrent)
    (repo / "a.txt").write_text("main-version\n")
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-am", "main edit"], check=True)

    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)
    result = mgr.apply_to_main(series.mbox, contract)
    assert result.status == "conflict"

    status = subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain"], text=True
    ).strip()
    assert status == ""
    assert not (repo / ".git" / "rebase-apply").exists()


def test_apply_to_main_clears_stale_rebase_apply(tmp_path):
    repo = _init_repo(tmp_path)
    # Simulate stale .git/rebase-apply from a prior crashed run
    stale = repo / ".git" / "rebase-apply"
    stale.mkdir()
    (stale / "stale-marker").write_text("x")

    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    contract["idempotency_token"] = "0123456789abcdef"
    contract["iter"] = 1
    contract["phase"] = 1
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "x\n")
    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)
    result = mgr.apply_to_main(series.mbox, contract)
    assert result.status == "applied"
    assert not (repo / ".git" / "rebase-apply").exists()


def test_apply_to_main_refuses_dirty_main(tmp_path):
    repo = _init_repo(tmp_path)
    (repo / "dirty.txt").write_text("untracked")  # dirty main
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    contract["idempotency_token"] = "feedfacefeedface"
    contract["iter"] = 1
    contract["phase"] = 1
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "x\n")
    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)
    with pytest.raises(_worktree.MainTreeDirtyError):
        mgr.apply_to_main(series.mbox, contract)


def test_cleanup_removes_worktree_and_branch(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    assert handle.path.exists()

    mgr.cleanup(handle, prune_branch=True)
    assert not handle.path.exists()
    branches = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "-a"], text=True
    )
    assert handle.branch not in branches


def test_cleanup_idempotent(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    mgr.cleanup(handle, prune_branch=True)
    # Second call must not raise
    mgr.cleanup(handle, prune_branch=True)


def test_rehydrate_reads_persisted_handle(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    original = mgr.create(contract, contract_dir=contract_dir)

    # Simulate PM restart: rehydrate from disk
    rehydrated = mgr.rehydrate(contract_dir)
    assert rehydrated == original


def test_rehydrate_returns_none_if_no_handle(tmp_path):
    mgr = _worktree.WorktreeManager(repo_root=tmp_path, worktree_base=tmp_path / "wt")
    contract_dir = tmp_path / "no-handle-here"
    contract_dir.mkdir()
    assert mgr.rehydrate(contract_dir) is None


def test_reap_orphans_removes_terminal_aged_worktrees(tmp_path):
    import json as _json
    import os
    import time

    import _status  # noqa: F401
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    state_dir = tmp_path / ".planning" / "auto-pilot"
    contracts_root = state_dir / "contracts" / "iter-1" / "phase-1" / "contract-1" / "round-1"
    contracts_root.mkdir(parents=True)
    contract = _fake_contract(repo, contracts_root)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contracts_root)
    # Worker status terminal + done.marker
    (contracts_root / "outputs" / "worker").mkdir(parents=True)
    (contracts_root / "outputs" / "worker" / "status.json").write_text(
        _json.dumps({"status": _status.WorkerStatus.DONE.value}))
    (contracts_root / "outputs" / "worker" / "done.marker").touch()
    # Backdate sentinel to look old
    old = time.time() - 48 * 3600
    os.utime(handle.path / ".auto-pilot-worktree", (old, old))

    reaped = mgr.reap_orphans(state_dir=state_dir, max_age_hours=24)
    assert handle.path in reaped


def test_reap_orphans_preserves_in_flight(tmp_path):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    state_dir = tmp_path / ".planning" / "auto-pilot"
    contracts_root = state_dir / "contracts" / "iter-1" / "phase-1" / "contract-1" / "round-1"
    contracts_root.mkdir(parents=True)
    contract = _fake_contract(repo, contracts_root)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contracts_root)
    # No status.json, no done.marker → in-flight
    reaped = mgr.reap_orphans(state_dir=state_dir, max_age_hours=0)
    assert handle.path not in reaped


def test_compute_merge_conflict_finding_hash():
    h1 = _worktree.compute_merge_conflict_finding_hash(["src/a.py", "src/b.py"])
    h2 = _worktree.compute_merge_conflict_finding_hash(["src/b.py", "src/a.py"])  # order-insensitive
    assert h1 == h2
    h3 = _worktree.compute_merge_conflict_finding_hash(["src/a.py"])
    assert h1 != h3


def test_apply_result_default_trailers_applied_true():
    assert _worktree.ApplyResult(status="applied").trailers_applied is True
    assert _worktree.ApplyResult(status="conflict").trailers_applied is True


def test_apply_to_main_marks_trailers_applied_false_when_amend_fails(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    contract["idempotency_token"] = "deadbeef00aabbcc"
    contract["iter"] = 2
    contract["phase"] = 3
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "x\n")
    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)

    orig = _worktree.subprocess.run

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        if isinstance(args, list) and "--amend" in args:
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="boom")
        return orig(args, **kwargs)

    monkeypatch.setattr(_worktree.subprocess, "run", fake_run)

    result = mgr.apply_to_main(series.mbox, contract)
    assert result.status == "applied"
    assert result.trailers_applied is False
    assert result.main_sha is not None

    # Amend was stubbed, so no trailer chain in the commit body
    log = subprocess.check_output(
        ["git", "-C", str(repo), "log", "-1", "--format=%B"], text=True
    )
    assert "auto-pilot-iter" not in log
