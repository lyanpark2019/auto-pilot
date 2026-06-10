"""End-to-end worktree lifecycle integration test."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _worktree  # noqa: E402


def _init_repo(tmp_path):
    """Init a tiny repo + contract fixture; return (repo, contract, mgr, contract_dir)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    # .planning/ created by main-apply.lock must not pollute `git status --porcelain`.
    (repo / ".gitignore").write_text(".planning/\n")
    (repo / "src.py").write_text("def f(): return 1\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore", "src.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    base = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()

    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = {
        "id": "iter-1/phase-1/contract-1/round-1",
        "iter": 1, "phase": 1,
        "idempotency_token": "abcd1234abcd1234",
        "snapshot_shas": {"base_sha": base, "spec": "0" * 64, "claude_md_chain": []},
    }
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    return repo, contract, mgr, contract_dir


def test_full_lifecycle(tmp_path):
    """create -> worker edits -> collect_patches -> apply_to_main -> cleanup."""
    repo, contract, mgr, contract_dir = _init_repo(tmp_path)

    # 1. create
    handle = mgr.create(contract, contract_dir=contract_dir)

    # 2. worker edits + single commit
    (handle.path / "src.py").write_text("def f(): return 42\n")
    subprocess.run(["git", "-C", str(handle.path), "commit", "-q", "-am", "fix f"], check=True)

    # 3. collect patches
    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)

    # 4. apply to main
    result = mgr.apply_to_main(series.mbox, contract)
    assert result.status == "applied"
    assert (repo / "src.py").read_text() == "def f(): return 42\n"

    # 5. trailers present
    log = subprocess.check_output(["git", "-C", str(repo), "log", "-1", "--format=%B"], text=True)
    assert "auto-pilot-iter: 1" in log
    assert "auto-pilot-contract: iter-1/phase-1/contract-1/round-1" in log

    # 6. cleanup
    mgr.cleanup(handle, prune_branch=True)
    assert not handle.path.exists()


def test_sentinel_excluded_from_status(tmp_path):
    """`.auto-pilot-worktree` sentinel must not appear in `git status --porcelain`.

    Live Step-0 regression — the untracked sentinel false-tripped
    assert_reviewer_was_scoped inside the worktree.
    """
    _repo, contract, mgr, contract_dir = _init_repo(tmp_path)
    handle = mgr.create(contract, contract_dir=contract_dir)
    porcelain = subprocess.check_output(
        ["git", "-C", str(handle.path), "status", "--porcelain"], text=True
    )
    assert ".auto-pilot-worktree" not in porcelain
    mgr.cleanup(handle, prune_branch=True)
