"""Tests for drift detector (scan_code + scan_docs + drift)."""
from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from pipeline import drift, scan_code, scan_docs


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "auth.py").write_text(
        '"""Auth module."""\n\n'
        'def login(user: str, password: str) -> bool:\n    return True\n\n'
        'class TokenStore:\n    pass\n'
    )
    (repo / "src" / "billing.py").write_text(
        '"""Billing."""\n\n'
        'def charge(amount: int, currency: str = "USD") -> str:\n    return ""\n'
    )
    (repo / "docs").mkdir()
    return repo


def test_scan_code_extracts_public(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = scan_code.scan_tree(repo)
    assert "src/auth.py" in result
    assert "login" in result["src/auth.py"]["public_functions"]
    assert "TokenStore" in result["src/auth.py"]["public_classes"]
    sig = result["src/auth.py"]["signatures"]["login"]
    assert "user: str" in sig
    assert "password: str" in sig
    assert "bool" in sig


def test_scan_docs_extracts_frontmatter_and_refs(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "auth.md").write_text(
        "---\ntype: module\nsource_files: [\"src/auth.py\"]\n---\n\n"
        "# Auth\n\nUses `login(user, pwd)` and `TokenStore`. See `src/auth.py:5`.\n"
    )
    result = scan_docs.scan_tree(repo)
    assert "docs/auth.md" in result
    info = result["docs/auth.md"]
    assert info["frontmatter"]["source_files"] == ["src/auth.py"]
    assert "src/auth.py:5" in info["code_refs"]
    assert "TokenStore" in info["symbol_mentions"]


def test_drift_detects_gap(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    # No docs at all — both modules should be gaps
    r = drift.detect(repo)
    gap_modules = {g["module"] for g in r.gap}
    assert "src/auth.py" in gap_modules
    assert "src/billing.py" in gap_modules


def test_drift_no_gap_when_doc_references(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "auth.md").write_text(
        "---\nsource_files: [\"src/auth.py\"]\n---\n\n# Auth\n"
    )
    r = drift.detect(repo)
    gap_modules = {g["module"] for g in r.gap}
    assert "src/auth.py" not in gap_modules
    assert "src/billing.py" in gap_modules


def test_drift_detects_orphan(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "stale.md").write_text(
        "# Stale\n\nSee `src/removed_module.py:10` for details.\n"
    )
    r = drift.detect(repo)
    assert any("removed_module.py" in o["ref"] for o in r.orphan)


def test_drift_detects_claim_drift(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "auth.md").write_text(
        "---\nsource_files: [\"src/auth.py\"]\n---\n\n# Auth\n\n"
        "Call `login(user)` to authenticate.\n"   # missing password arg
    )
    r = drift.detect(repo)
    assert any(c["symbol"] == "login" for c in r.claim_drift)


def test_drift_skips_manual_pages(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "docs" / "stale.md").write_text(
        "---\nmanual_edit: true\n---\n\nSee `removed.py`.\n"
    )
    r = drift.detect(repo)
    assert not any("removed.py" in o["ref"] for o in r.orphan)


def test_drift_excludes_tests_from_public_api(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_x.py").write_text("def test_foo(): pass\n")
    (repo / "src").mkdir()
    (repo / "src" / "real.py").write_text("def public_fn(): pass\n")
    r = drift.detect(repo)
    gap_modules = {g["module"] for g in r.gap}
    assert "tests/test_x.py" not in gap_modules
    assert "src/real.py" in gap_modules
