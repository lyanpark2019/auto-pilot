"""Regression tests for the strict mypy surface."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mypy_scope_includes_vault_pilots() -> None:
    config = (REPO_ROOT / "mypy.ini").read_text(encoding="utf-8")

    assert "vault/pipeline/canvas.py" in config
    assert "vault/sources/code.py" in config
