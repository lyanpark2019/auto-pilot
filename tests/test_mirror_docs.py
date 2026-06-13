"""Tests for scripts/docs/mirror_docs.py — repo-docs → vault-root mirror."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "mirror_docs",
    Path(__file__).resolve().parent.parent / "scripts" / "docs" / "mirror_docs.py",
)
assert _SPEC and _SPEC.loader
mirror_docs = importlib.util.module_from_spec(_SPEC)
sys.modules["mirror_docs"] = mirror_docs  # dataclass needs the module registered
_SPEC.loader.exec_module(mirror_docs)


def _make_repo(tmp: Path) -> Path:
    repo = tmp / "proj"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "architecture.md").write_text(
        "---\ntype: architecture\nsource_commit: old111\nmanual_edit: true\n---\n\n# Arch\nbody\n"
    )
    (docs / "perf-budget.md").write_text(
        "---\ntype: runbook\nsource_commit: old222\nmanual_edit: false\n---\n\n# Perf\nbudget\n"
    )
    (docs / "plain.md").write_text("# Plain\nno frontmatter\n")
    (docs / "README.md").write_text("# docs readme (should be excluded)\n")
    (repo / "README.md").write_text("# root readme\ncanonical\n")
    (repo / "CLAUDE.md").write_text("# root claude\n")
    return repo


def test_flattens_top_level_docs_to_wiki_root(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wiki = tmp_path / "wiki" / "proj"
    mirror_docs.mirror_docs(repo, wiki, commit="abc123", synced="2026-06-14")
    assert (wiki / "architecture.md").exists()
    assert (wiki / "perf-budget.md").exists()
    assert (wiki / "plain.md").exists()
    assert (wiki / "README.md").read_text().startswith("---")  # stamped root readme
    assert (wiki / "CLAUDE.md").exists()


def test_overwrites_manual_edit_vault_page(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wiki = tmp_path / "wiki" / "proj"
    wiki.mkdir(parents=True)
    # pre-existing stale vault page marked manual_edit:true — must be overwritten
    (wiki / "architecture.md").write_text(
        "---\nmanual_edit: true\n---\n# STALE Opus 4.7\n"
    )
    mirror_docs.mirror_docs(repo, wiki, commit="abc123", synced="2026-06-14")
    out = (wiki / "architecture.md").read_text()
    assert "STALE" not in out
    assert "# Arch" in out


def test_stamps_source_commit_to_head(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wiki = tmp_path / "wiki" / "proj"
    mirror_docs.mirror_docs(repo, wiki, commit="HEADSHA999", synced="2026-06-14")
    arch = (wiki / "architecture.md").read_text()
    assert "source_commit: HEADSHA999" in arch
    assert "old111" not in arch
    assert "last_synced: 2026-06-14" in arch
    # perf-budget too
    assert "source_commit: HEADSHA999" in (wiki / "perf-budget.md").read_text()


def test_adds_frontmatter_to_plain_page(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wiki = tmp_path / "wiki" / "proj"
    mirror_docs.mirror_docs(repo, wiki, commit="c1", synced="2026-06-14")
    plain = (wiki / "plain.md").read_text()
    assert plain.startswith("---\n")
    assert "source_commit: c1" in plain
    assert "# Plain" in plain


def test_root_readme_wins_over_docs_readme(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wiki = tmp_path / "wiki" / "proj"
    mirror_docs.mirror_docs(repo, wiki, commit="c1", synced="2026-06-14")
    readme = (wiki / "README.md").read_text()
    assert "root readme" in readme
    assert "should be excluded" not in readme


def test_removes_redundant_docs_subdir(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wiki = tmp_path / "wiki" / "proj"
    stale = wiki / "docs"
    stale.mkdir(parents=True)
    (stale / "architecture.md").write_text("# duplicate layout\n")
    report = mirror_docs.mirror_docs(repo, wiki, commit="c1", synced="2026-06-14")
    assert not stale.exists()
    assert report.docs_subdir_removed is True


def test_regenerates_index(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wiki = tmp_path / "wiki" / "proj"
    mirror_docs.mirror_docs(repo, wiki, commit="c1", synced="2026-06-14")
    idx = (wiki / "index.md").read_text()
    assert "auto-generated" in idx
    assert "[[architecture]]" in idx


def test_leaves_vault_only_content_untouched(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wiki = tmp_path / "wiki" / "proj"
    nodes = wiki / "nodes"
    nodes.mkdir(parents=True)
    (nodes / "graph.md").write_text("# vault-only\n")
    mirror_docs.mirror_docs(repo, wiki, commit="c1", synced="2026-06-14")
    assert (nodes / "graph.md").read_text() == "# vault-only\n"


def test_main_cli_resolves_commit(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wiki = tmp_path / "wiki" / "proj"
    rc = mirror_docs.main(["--repo", str(repo), "--wiki", str(wiki), "--commit", "z9"])
    assert rc == 0
    assert "source_commit: z9" in (wiki / "architecture.md").read_text()
