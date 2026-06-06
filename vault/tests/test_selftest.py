"""Tests for plugin selftest: ensures the real plugin passes its own checks."""
from __future__ import annotations

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
