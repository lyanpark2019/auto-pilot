"""Fixture self-test for skills/doc-management/scripts/check_design_doc_freshness.py.

Covers the L3 freshness contract: STALE detection, frontmatter contract WARN
(type/topic/source_commit/manual_edit — doc-management-system.md section 5),
manual_edit skip, and the always-exit-0 WARN-gate invariant.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent
    / "skills" / "doc-management" / "scripts" / "check_design_doc_freshness.py"
)


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def _run(repo: Path, *roots: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), *roots],
        cwd=repo, capture_output=True, text=True, timeout=30,
    )


def _doc(repo: Path, name: str, frontmatter: dict[str, str], body: str) -> Path:
    lines = ["---"] + [f"{k}: {v}" for k, v in frontmatter.items()] + ["---", "", body]
    doc = repo / "docs" / name
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text("\n".join(lines))
    return doc


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Tmp git repo with one committed source file under an allowlisted prefix."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    src = tmp_path / "scripts" / "foo.py"
    src.parent.mkdir()
    src.write_text("x = 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _full_meta(commit: str) -> dict[str, str]:
    return {"type": "design", "topic": "foo", "source_commit": commit, "manual_edit": "false"}


class TestFreshness:
    def test_fresh_doc_no_stale_no_warn(self, repo: Path):
        commit = _git(repo, "rev-parse", "HEAD")
        _doc(repo, "a.md", _full_meta(commit), "Covers `scripts/foo.py`.")
        r = _run(repo, "docs")
        assert r.returncode == 0
        flagged = [ln for ln in r.stdout.splitlines() if ln.startswith(("STALE", "WARN docs"))]
        assert flagged == []
        assert "1 doc(s) scanned, 0 STALE, 0 WARN" in r.stdout

    def test_stale_when_cited_source_changes(self, repo: Path):
        commit = _git(repo, "rev-parse", "HEAD")
        _doc(repo, "a.md", _full_meta(commit), "Covers `scripts/foo.py`.")
        (repo / "scripts" / "foo.py").write_text("x = 2\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "change source")
        r = _run(repo, "docs")
        assert r.returncode == 0
        assert "STALE" in r.stdout and "scripts/foo.py" in r.stdout

    def test_manual_edit_skipped(self, repo: Path):
        commit = _git(repo, "rev-parse", "HEAD")
        meta = _full_meta(commit) | {"manual_edit": "true"}
        _doc(repo, "a.md", meta, "Covers `scripts/foo.py`.")
        (repo / "scripts" / "foo.py").write_text("x = 3\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "change source")
        r = _run(repo, "docs")
        assert r.returncode == 0
        assert "SKIP" in r.stdout
        assert not [ln for ln in r.stdout.splitlines() if ln.startswith("STALE")]


class TestFrontmatterContract:
    def test_missing_keys_warn_listed(self, repo: Path):
        commit = _git(repo, "rev-parse", "HEAD")
        _doc(repo, "a.md", {"source_commit": commit, "manual_edit": "false"},
             "Covers `scripts/foo.py`.")
        r = _run(repo, "docs")
        assert r.returncode == 0
        warn = [ln for ln in r.stdout.splitlines() if ln.startswith("WARN")]
        assert len(warn) == 1
        assert "type" in warn[0] and "topic" in warn[0]
        assert "source_commit" not in warn[0] and "manual_edit" not in warn[0]

    def test_missing_source_commit_single_warn_no_crash(self, repo: Path):
        _doc(repo, "a.md", {"type": "design", "topic": "foo", "manual_edit": "false"},
             "Covers `scripts/foo.py`.")
        r = _run(repo, "docs")
        assert r.returncode == 0
        warn = [ln for ln in r.stdout.splitlines() if ln.startswith("WARN docs")]
        assert len(warn) == 1 and "source_commit" in warn[0]
        assert "1 doc(s) scanned, 0 STALE, 1 WARN" in r.stdout

    def test_empty_value_counts_as_missing(self, repo: Path):
        commit = _git(repo, "rev-parse", "HEAD")
        _doc(repo, "a.md",
             {"type": "", "topic": "foo", "source_commit": commit, "manual_edit": "false"},
             "Covers `scripts/foo.py`.")
        r = _run(repo, "docs")
        assert r.returncode == 0
        assert any("missing key(s): type" in ln for ln in r.stdout.splitlines())

    def test_no_frontmatter_warns_all_four(self, repo: Path):
        doc = repo / "docs" / "a.md"
        doc.parent.mkdir(exist_ok=True)
        doc.write_text("No frontmatter here. Covers `scripts/foo.py`.\n")
        r = _run(repo, "docs")
        assert r.returncode == 0
        warn = [ln for ln in r.stdout.splitlines() if ln.startswith("WARN docs")]
        assert len(warn) == 1
        for key in ("type", "topic", "source_commit", "manual_edit"):
            assert key in warn[0]

    def test_contract_warn_still_fires_for_manual_edit_docs(self, repo: Path):
        _doc(repo, "a.md", {"manual_edit": "true"}, "Hand-written page.")
        r = _run(repo, "docs")
        assert r.returncode == 0
        assert any("missing key(s)" in ln for ln in r.stdout.splitlines())
        assert "SKIP" in r.stdout
