"""Tests for source adapter registry + code adapter (no external CLI needed)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from sources import _adapter  # noqa: E402
from sources.notebooklm import _classify_title  # noqa: E402


def setup_module(module):
    _adapter._autodiscover()


def test_registry_has_known_adapters():
    assert "notebooklm" in _adapter.REGISTRY
    assert "code" in _adapter.REGISTRY


def test_get_unknown_raises():
    import pytest
    with pytest.raises(ValueError, match="unknown source adapter"):
        _adapter.get("nonexistent")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("team_mlb_dodgers_2026", "match-analysis"),
        ("농식품 비관세 장벽", "agri-trade"),
        ("로또 확률", "lotto"),
        ("PickL Architecture", "pickl-projects"),
        ("sportic365 auth envelope", "sportic-projects"),
        ("temp-check", "archive"),
        ("Claude Code prompt harness", "ai-libraries"),
        ("OpenAI schema output control", "llm-research"),
        ("unmatched notebook", "uncategorized"),
    ],
)
def test_notebooklm_title_classifier_examples(title: str, expected: str) -> None:
    assert _classify_title(title) == expected


def test_code_adapter_discover(tmp_path: Path) -> None:
    AdapterCls = _adapter.get("code")
    adapter = AdapterCls()

    # Build a fake repo
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "auth" / "login.py").write_text("def login(): ...")
    (tmp_path / "src" / "auth" / "tokens.py").write_text("def issue(): ...")
    (tmp_path / "src" / "auth" / "permissions.py").write_text("def check(): ...")
    (tmp_path / "src" / "billing").mkdir(parents=True)
    (tmp_path / "src" / "billing" / "stripe.py").write_text("def charge(): ...")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "bad.js").write_text("// noise")

    items = adapter.discover(tmp_path)
    paths = [it.id for it in items]
    assert any("auth/login.py" in p for p in paths)
    assert any("billing/stripe.py" in p for p in paths)
    assert not any("node_modules" in p for p in paths)


def test_code_adapter_excludes_agent_worktrees(tmp_path: Path) -> None:
    """Agent worktrees are near-duplicate source copies; discover must skip them
    so buckets/graph are not polluted with ~2x phantom module pages."""
    AdapterCls = _adapter.get("code")
    adapter = AdapterCls()

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "real.py").write_text("def real(): ...")
    for wt in (".codex-worktrees", ".worktrees"):
        (tmp_path / wt / "w1" / "app").mkdir(parents=True)
        (tmp_path / wt / "w1" / "app" / "dup.py").write_text("def dup(): ...")
    (tmp_path / ".claude" / "worktrees" / "agent-x" / "app").mkdir(parents=True)
    (tmp_path / ".claude" / "worktrees" / "agent-x" / "app" / "dup.py").write_text("def dup(): ...")

    paths = [it.id for it in adapter.discover(tmp_path)]
    assert any("app/real.py" in p for p in paths)
    assert not any("worktree" in p for p in paths)


def test_code_adapter_classify_merges_tiny(tmp_path: Path) -> None:
    AdapterCls = _adapter.get("code")
    adapter = AdapterCls()
    (tmp_path / "auth").mkdir()
    for n in ("a.py", "b.py", "c.py"):
        (tmp_path / "auth" / n).write_text("x")
    (tmp_path / "tiny").mkdir()
    (tmp_path / "tiny" / "x.py").write_text("x")

    items = adapter.discover(tmp_path)
    buckets = adapter.classify(items)
    assert "auth" in buckets
    assert "tiny" not in buckets
    assert "misc" in buckets


def test_code_adapter_bootstrap_creates_tree(tmp_path: Path) -> None:
    AdapterCls = _adapter.get("code")
    adapter = AdapterCls()
    (tmp_path / "auth").mkdir()
    for n in ("a.py", "b.py", "c.py"):
        (tmp_path / "auth" / n).write_text("x")

    vault = tmp_path / "vault"
    items = adapter.discover(tmp_path)
    buckets = adapter.classify(items)
    adapter.bootstrap(vault, buckets)

    assert (vault / "auth" / "index.md").exists()
    assert (vault / "auth" / "modules").is_dir()
    assert (vault / "meta" / "categories.json").exists()
    assert (vault / "index.md").exists()
