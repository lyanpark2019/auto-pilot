"""Tests for plugin selftest: ensures the real plugin passes its own checks."""
from __future__ import annotations

from pathlib import Path

import selftest


def test_plugin_self_passes() -> None:
    """The plugin itself must pass selftest at all times."""
    import os
    selftest.os = os  # selftest sets os in main(); set it for direct call too
    n_fail, checks = selftest.run_all()
    failed = [(c.name, c.failures) for c in checks if not c.ok()]
    assert n_fail == 0, f"Plugin failed selftest:\n{failed}"


def test_run_all_returns_list() -> None:
    n_fail, checks = selftest.run_all()
    assert isinstance(checks, list)
    assert len(checks) >= 6
    names = {c.name for c in checks}
    assert {"manifest", "agents", "scripts", "rubric"}.issubset(names)


def test_vault_commands_roster() -> None:
    """VAULT_COMMANDS must match the consolidated 4-command set."""
    assert selftest.VAULT_COMMANDS == {"vault-build", "vault-score", "vault-dashboard", "vault-selftest"}


def test_vault_agents_roster() -> None:
    """VAULT_AGENTS must match the consolidated 5-agent set."""
    assert selftest.VAULT_AGENTS == {
        "vault-edge-curator", "vault-graph-enricher", "vault-knowledge-author",
        "vault-structure-curator", "vault-pm-orchestrator",
    }


def test_all_agents_name_matches_stem() -> None:
    """Every non-underscore agents/*.md must have frontmatter name == file stem."""
    import yaml
    agents_dir = selftest.PLUGIN_ROOT / "agents"
    for f in agents_dir.glob("*.md"):
        if f.name.startswith("_"):
            continue
        text = f.read_text()
        m = selftest.FM_PATTERN.match(text)
        assert m, f"{f.name}: missing frontmatter"
        fm = yaml.safe_load(m.group(1))
        assert isinstance(fm, dict), f"{f.name}: frontmatter not a dict"
        assert fm.get("name") == f.stem, (
            f"{f.name}: name '{fm.get('name')}' != stem '{f.stem}'"
        )


def test_check_agents_catches_name_drift(tmp_path: Path) -> None:
    """Widened namecheck catches non-vault agent frontmatter drift (synthetic tree)."""
    import pytest
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()

    # Write the 5 VAULT_AGENTS with valid name==stem frontmatter (roster check passes)
    for stem in selftest.VAULT_AGENTS:
        (agents_dir / f"{stem}.md").write_text(
            f"---\nname: {stem}\ndescription: test\n---\nbody\n"
        )

    # Write a core agent whose name drifts from its stem
    (agents_dir / "worker.md").write_text(
        "---\nname: auto-pilot-worker\ndescription: test\n---\nbody\n"
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(selftest, "PLUGIN_ROOT", tmp_path)
    try:
        result = selftest._check_agents()
    finally:
        monkeypatch.undo()

    assert not result.ok(), "Expected failure for name!=stem drift"
    assert any(
        "worker.md" in msg and "stem" in msg for msg in result.failures
    ), f"Expected worker.md stem mismatch in failures; got: {result.failures}"
