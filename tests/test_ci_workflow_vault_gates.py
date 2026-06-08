from __future__ import annotations

from pathlib import Path


CI = Path(".github/workflows/ci.yml")
REQUIREMENTS_DEV = Path("requirements-dev.txt")


def _ci_text() -> str:
    return CI.read_text(encoding="utf-8")


def test_ci_ruff_gate_includes_vault_and_hooks_trees() -> None:
    text = _ci_text()

    assert "python -m ruff check scripts/ tests/ hooks/ vault/" in text


def test_ci_runs_vault_pytest_suite() -> None:
    text = _ci_text()

    assert "cd vault && python -m pytest tests/ -q" in text


def test_ci_coverage_gate_matches_local_quality_floor() -> None:
    text = _ci_text()

    assert "--cov=scripts --cov-fail-under=80" in text
    assert "--cov-fail-under=75" not in text


def test_ci_runs_script_style_hook_selftests() -> None:
    text = _ci_text()

    assert "python3 hooks/test_guard_destructive.py" in text
    assert "python3 hooks/test_codex_conductor_guard.py" in text
    assert "python3 hooks/test_notebooklm_delete_gate.py" in text


def test_ci_installs_vault_pytest_dependencies() -> None:
    requirements = REQUIREMENTS_DEV.read_text(encoding="utf-8")

    assert "PyYAML" in requirements


def test_ci_uses_node24_action_majors() -> None:
    text = _ci_text()

    assert "actions/checkout@v4" not in text
    assert "actions/setup-python@v5" not in text
    assert "actions/checkout@v5" in text
    assert "actions/setup-python@v6" in text
