"""Subprocess tests for scripts/ap-worktree.sh (operator worktree helper).

The helper is invoked via subprocess (not the Claude Code Bash tool), so the
PreToolUse hooks do not intercept it here. Tests branch off a LOCAL ``main``
(AP_WORKTREE_BASE_REF=main, no "/") so no network fetch happens.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent / "scripts" / "ap-worktree.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _init_repo(path: Path) -> None:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@t.t")
    _git(path, "config", "user.name", "t")
    (path / "f.txt").write_text("hi\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-qm", "init")


def _run(args: list[str], *, cwd: Path, base: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "AP_WORKTREE_BASE": str(base), "AP_WORKTREE_BASE_REF": "main"}
    return subprocess.run(
        ["bash", str(HELPER), *args],
        cwd=str(cwd), env=env, capture_output=True, text=True,
    )


def _branch(wt: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(wt), "branch", "--show-current"],
        capture_output=True, text=True,
    ).stdout.strip()


def test_new_creates_worktree_on_dated_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = tmp_path / "wts"
    base.mkdir()
    r = _run(["new", "foo"], cwd=repo, base=base)
    assert r.returncode == 0, r.stderr
    wt = base / "ap-foo"
    assert wt.is_dir()
    assert _branch(wt).startswith("fix/foo-")
    # guidance names the -C drive pattern and the explicit-refspec push
    assert "git -C" in r.stdout and "push -u origin" in r.stdout


def test_new_rejects_existing_slug(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = tmp_path / "wts"
    base.mkdir()
    assert _run(["new", "dup"], cwd=repo, base=base).returncode == 0
    r2 = _run(["new", "dup"], cwd=repo, base=base)
    assert r2.returncode == 2
    assert "already exists" in r2.stderr


def test_done_removes_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = tmp_path / "wts"
    base.mkdir()
    _run(["new", "bar"], cwd=repo, base=base)
    wt = base / "ap-bar"
    assert wt.is_dir()
    r = _run(["done", "bar"], cwd=repo, base=base)
    assert r.returncode == 0, r.stderr
    assert not wt.exists()
    assert "git branch -D fix/bar-" in r.stdout  # cleanup reminder


def test_done_missing_worktree_errors(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = tmp_path / "wts"
    base.mkdir()
    r = _run(["done", "nope"], cwd=repo, base=base)
    assert r.returncode == 2
    assert "no worktree" in r.stderr


def test_prune_removes_orphan_keeps_live(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = tmp_path / "wts"
    base.mkdir()
    # one live worktree
    _run(["new", "live"], cwd=repo, base=base)
    live = base / "ap-live"
    # one manual orphan dir (not a registered worktree)
    orphan = base / "ap-orphan"
    orphan.mkdir()
    r = _run(["prune"], cwd=repo, base=base)
    assert r.returncode == 0, r.stderr
    # regression: a live worktree must survive prune even though
    # `git worktree list` reports a canonical (symlink-resolved) path
    assert live.is_dir()
    assert not orphan.exists()


def test_usage_without_subcommand_exits_1(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = tmp_path / "wts"
    base.mkdir()
    r = _run([], cwd=repo, base=base)
    assert r.returncode == 1
    assert "usage:" in r.stderr
