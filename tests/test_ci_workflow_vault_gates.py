from __future__ import annotations

from pathlib import Path


CI = Path(".github/workflows/ci.yml")


def _ci_text() -> str:
    return CI.read_text(encoding="utf-8")


def test_ci_ruff_gate_includes_vault_tree() -> None:
    text = _ci_text()

    assert "python -m ruff check scripts/ tests/ vault/" in text


def test_ci_runs_vault_pytest_suite() -> None:
    text = _ci_text()

    assert "cd vault && python -m pytest tests/ -q" in text
