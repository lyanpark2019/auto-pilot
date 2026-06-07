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


def _write_minimal_assets(repo: Path) -> None:
    skill = repo / "skills" / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: alpha\n---\n")
    agents = repo / "agents"
    agents.mkdir()
    (agents / "worker.md").write_text("# worker\n")
    commands = repo / "commands"
    commands.mkdir()
    (commands / "run.md").write_text("# run\n")
    hooks = repo / "hooks"
    hooks.mkdir()
    (hooks / "guard.sh").write_text("#!/usr/bin/env bash\n")
    codex_skill = repo / "codex" / "skills" / "audit"
    codex_skill.mkdir(parents=True)


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


class TestAssetCountClaims:
    def test_live_asset_count_mismatch_is_violation(self, repo: Path) -> None:
        _write_minimal_assets(repo)
        (repo / "docs" / "guide.md").write_text(
            "Live asset counts (from `scripts/build_dashboard_data.collect_assets()`): "
            "2 skills · 1 agents · 1 commands · 1 hooks · 1 codex-skills = "
            "6 assets total.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "asset count mismatch" in r.stdout
        assert "skills: said 2, actual 1" in r.stdout
        assert "assets: said 6, actual 5" in r.stdout

    def test_source_comment_collect_assets_count_mismatch_is_violation(self, repo: Path) -> None:
        (repo / "scripts" / "registry.py").write_text(
            "# registry at 80 vs build_dashboard_data.collect_assets' canonical 77\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "scripts/registry.py:1" in r.stdout
        assert "asset count mismatch" in r.stdout

    def test_historical_asset_count_snapshot_is_allowed(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "Historical Round-1 snapshot (113 assets, recorded before consolidation).\n"
        )
        r = _run(repo)
        assert r.returncode == 0

    def test_asset_total_includes_skill_shells(self, repo: Path) -> None:
        (repo / "skills" / "retired-shell").mkdir(parents=True)
        (repo / "docs" / "guide.md").write_text(
            "Live asset counts (from `scripts/build_dashboard_data.collect_assets()`): "
            "0 skills · 0 agents · 0 commands · 0 hooks · 0 codex-skills = "
            "1 assets total.\n"
        )
        r = _run(repo)
        assert r.returncode == 0

    def test_asset_counts_use_build_dashboard_data_collect_assets(self, repo: Path) -> None:
        (repo / "scripts" / "build_dashboard_data.py").write_text(
            "def collect_assets():\n"
            "    return [\n"
            "        {'type': 'skill', 'name': 'alpha'},\n"
            "        {'type': 'hook', 'name': 'one.sh'},\n"
            "        {'type': 'hook', 'name': 'two.py'},\n"
            "    ]\n"
        )
        (repo / "docs" / "guide.md").write_text(
            "Live asset counts (from `scripts/build_dashboard_data.collect_assets()`): "
            "1 skills · 0 agents · 0 commands · 2 hooks · 0 codex-skills = "
            "3 assets total.\n"
        )
        r = _run(repo)
        assert r.returncode == 0


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
