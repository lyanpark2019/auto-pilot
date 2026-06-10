"""Tests for scripts/_discovery.py — deterministic graphify-context discovery seam."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _discovery  # noqa: E402


@pytest.fixture()
def repo(tmp_path):
    """Tiny git repo with one commit; returns (repo_root, state_dir)."""
    r = tmp_path / "repo"
    r.mkdir()
    subprocess.run(["git", "-C", str(r), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(r), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(r), "config", "user.name", "T"], check=True)
    (r / "src").mkdir()
    (r / "src" / "a.py").write_text("a = 1\n")
    (r / "README.md").write_text("readme\n")
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "init"], check=True)
    state = tmp_path / "state"
    state.mkdir()
    return r, state


def _commit(repo_root: Path, relpath: str, content: str) -> None:
    p = repo_root / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    subprocess.run(["git", "-C", str(repo_root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo_root), "commit", "-q", "-m", f"edit {relpath}"], check=True)


def _head(repo_root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
    ).strip()


def test_record_writes_provenance(repo):
    repo_root, state = repo
    payload = _discovery.record_provenance(
        repo_root=repo_root, state_dir=state, graphify_version="1.2.0"
    )
    on_disk = json.loads((state / _discovery.PROVENANCE_FILE).read_text())
    assert on_disk == payload
    assert on_disk["build_commit"] == _head(repo_root)
    assert on_disk["graphify_version"] == "1.2.0"
    assert "recorded_at" in on_disk


def test_check_never_recorded(repo):
    repo_root, state = repo
    f = _discovery.check_freshness(
        repo_root=repo_root, state_dir=state, graphify_version="1.2.0"
    )
    assert f.fresh is False
    assert f.reason == "never-recorded"


def test_check_same_commit_fresh(repo):
    repo_root, state = repo
    _discovery.record_provenance(repo_root=repo_root, state_dir=state, graphify_version="1.2.0")
    f = _discovery.check_freshness(
        repo_root=repo_root, state_dir=state, graphify_version="1.2.0",
        scope_files=("src/a.py",),
    )
    assert f.fresh is True
    assert f.reason == "same-commit"


def test_check_version_changed_stale(repo):
    repo_root, state = repo
    _discovery.record_provenance(repo_root=repo_root, state_dir=state, graphify_version="1.2.0")
    f = _discovery.check_freshness(
        repo_root=repo_root, state_dir=state, graphify_version="2.0.0"
    )
    assert f.fresh is False
    assert f.reason == "version-changed"


def test_check_scope_intersects_stale(repo):
    repo_root, state = repo
    _discovery.record_provenance(repo_root=repo_root, state_dir=state, graphify_version="1.2.0")
    _commit(repo_root, "src/a.py", "a = 2\n")
    f = _discovery.check_freshness(
        repo_root=repo_root, state_dir=state, graphify_version="1.2.0",
        scope_files=("src/a.py",),
    )
    assert f.fresh is False
    assert f.reason == "scope-intersects"
    assert "src/a.py" in f.changed_files


def test_check_no_scope_overlap_fresh(repo):
    """Diff-relevance, NOT sha-equality: unrelated commits must not force regen."""
    repo_root, state = repo
    _discovery.record_provenance(repo_root=repo_root, state_dir=state, graphify_version="1.2.0")
    _commit(repo_root, "README.md", "changed\n")
    f = _discovery.check_freshness(
        repo_root=repo_root, state_dir=state, graphify_version="1.2.0",
        scope_files=("src/a.py",),
    )
    assert f.fresh is True
    assert f.reason == "no-scope-overlap"


def test_check_dir_prefix_scope_matches(repo):
    repo_root, state = repo
    _discovery.record_provenance(repo_root=repo_root, state_dir=state, graphify_version="1.2.0")
    _commit(repo_root, "src/new.py", "n = 1\n")
    f = _discovery.check_freshness(
        repo_root=repo_root, state_dir=state, graphify_version="1.2.0",
        scope_files=("src/",),
    )
    assert f.fresh is False
    assert f.reason == "scope-intersects"
    assert "src/new.py" in f.changed_files


def test_check_changed_no_scope_conservative_stale(repo):
    """No scope provided + commits differ → conservative stale (PM decides)."""
    repo_root, state = repo
    _discovery.record_provenance(repo_root=repo_root, state_dir=state, graphify_version="1.2.0")
    _commit(repo_root, "README.md", "changed\n")
    f = _discovery.check_freshness(
        repo_root=repo_root, state_dir=state, graphify_version="1.2.0"
    )
    assert f.fresh is False
    assert f.reason == "changed-no-scope"
    assert "README.md" in f.changed_files


def test_check_unknown_build_commit_stale(repo):
    repo_root, state = repo
    (state / _discovery.PROVENANCE_FILE).write_text(json.dumps({
        "build_commit": "f" * 40,
        "graphify_version": "1.2.0",
        "recorded_at": "2026-06-10T00:00:00+00:00",
    }))
    f = _discovery.check_freshness(
        repo_root=repo_root, state_dir=state, graphify_version="1.2.0"
    )
    assert f.fresh is False
    assert f.reason == "build-commit-unknown"


def test_check_corrupt_provenance_stale(repo):
    repo_root, state = repo
    (state / _discovery.PROVENANCE_FILE).write_text("{not json")
    f = _discovery.check_freshness(
        repo_root=repo_root, state_dir=state, graphify_version="1.2.0"
    )
    assert f.fresh is False
    assert f.reason == "provenance-corrupt"
