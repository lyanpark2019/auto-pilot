"""Regression tests for the strict mypy surface."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_mypy_scope_includes_vault_pilots() -> None:
    config = (REPO_ROOT / "mypy.ini").read_text(encoding="utf-8")
    expected = {
        "vault/pipeline/canvas.py",
        "vault/sources/code.py",
        "vault/sources/_excludes.py",
        "vault/pipeline/bases.py",
        "vault/pipeline/scan_code.py",
        "vault/pipeline/state.py",
        "vault/pipeline/scan_docs.py",
        "vault/scripts/lockfile.py",
        "vault/pipeline/dispatch.py",
        "vault/pipeline/loop.py",
        "vault/pipeline/self_improve.py",
        "vault/pipeline/fix.py",
        "vault/scripts/dashboard_data.py",
        "vault/sources/notebooklm.py",
    }

    for path in expected:
        assert path in config
