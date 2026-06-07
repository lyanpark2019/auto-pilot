"""Tests for scripts/docs/check_doc_reference_integrity.py."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent
    / "scripts" / "docs" / "check_doc_reference_integrity.py"
)


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--root", str(root)],
        capture_output=True, text=True, timeout=30,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Minimal repo structure with one Python file under scripts/."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    target = scripts / "helper.py"
    target.write_text("def foo():\n    pass\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    return tmp_path


class TestValidCitations:
    def test_no_citations_exits_clean(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text("No citations here.\n")
        r = _run(repo)
        assert r.returncode == 0
        assert "0 violations" in r.stdout

    def test_valid_file_and_line_exits_clean(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "See `scripts/helper.py:1` for the definition.\n"
        )
        r = _run(repo)
        assert r.returncode == 0

    def test_valid_range_citation_exits_clean(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "Covered in `scripts/helper.py:1-2` (both lines).\n"
        )
        r = _run(repo)
        assert r.returncode == 0


class TestViolations:
    def test_missing_file_is_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "See `scripts/gone.py:1` which is deleted.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "scripts/gone.py:1" in r.stdout
        assert "file not found" in r.stdout

    def test_line_beyond_eof_is_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "See `scripts/helper.py:999` for the definition.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "scripts/helper.py:999" in r.stdout
        assert "999 >" in r.stdout

    def test_range_end_beyond_eof_is_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "Range `scripts/helper.py:1-999` is too wide.\n"
        )
        r = _run(repo)
        assert r.returncode == 1

    def test_bare_filename_without_directory_is_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "See `helper.py:1` — bare name, no directory prefix.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "helper.py:1" in r.stdout

    def test_suggestion_shows_file_length(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "`scripts/helper.py:999` is past EOF.\n"
        )
        r = _run(repo)
        assert "has 2 lines" in r.stdout


class TestIgnoreMarker:
    def test_cite_ignore_suppresses_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "Historical: `scripts/gone.py:1` <!-- cite-ignore -->\n"
        )
        r = _run(repo)
        assert r.returncode == 0
        assert "0 violations" in r.stdout


class TestScanScope:
    def test_claude_md_at_root_is_scanned(self, repo: Path) -> None:
        (repo / "CLAUDE.md").write_text(
            "See `scripts/gone.py:1` for context.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "CLAUDE.md" in r.stdout

    def test_dot_claude_docs_scanned(self, repo: Path) -> None:
        dot_claude = repo / ".claude"
        dot_claude.mkdir()
        (dot_claude / "notes.md").write_text(
            "`scripts/gone.py:1` — stale.\n"
        )
        r = _run(repo)
        assert r.returncode == 1

    def test_worktrees_are_excluded(self, repo: Path) -> None:
        wt = repo / ".claude" / "worktrees" / "agent-abc"
        wt.mkdir(parents=True)
        (wt / "stale.md").write_text(
            "`scripts/gone.py:1` — inside worktree, should be skipped.\n"
        )
        r = _run(repo)
        assert r.returncode == 0

    def test_multiple_violations_all_listed(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "`scripts/gone.py:1`\n`scripts/also-gone.py:2`\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "2 violation" in r.stdout
