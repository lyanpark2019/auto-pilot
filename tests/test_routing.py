from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _routing  # noqa: E402

REPO_YAML = (Path(__file__).resolve().parent.parent
             / "skills" / "auto-pilot" / "references" / "model-routing.yaml")


@pytest.mark.parametrize("tier,effort", [
    ("none", "low"), ("low", "low"), ("medium", "medium"),
    ("high", "high"), ("critical", "xhigh"),
])
def test_effort_for_tier_matrix(tier, effort):
    assert _routing.effort_for_tier(tier) == effort


def test_effort_for_unknown_tier_defaults_medium():
    """Unknown tier must fail-open to medium — codex effort is advisory, never a crash."""
    assert _routing.effort_for_tier("bogus") == "medium"


@pytest.mark.parametrize("effort,lower", [
    ("xhigh", "high"), ("high", "medium"), ("medium", "low"),
    ("low", "low"), ("bogus", "low"),
])
def test_lower_effort_ladder(effort, lower):
    assert _routing.lower_effort(effort) == lower


def test_codex_timeouts_from_repo_yaml():
    timeout_s, retry_s = _routing.codex_timeouts()
    assert timeout_s == 240
    assert retry_s == 180


def test_verifier_min_tier():
    assert _routing.verifier_min_tier() == "opus"


@pytest.mark.parametrize("token,rank", [
    ("fable", 0), ("opus", 1), ("sonnet", 3), ("haiku", 4),
])
def test_model_rank(token, rank):
    assert _routing.model_rank(token) == rank


def test_model_rank_unknown_is_none():
    assert _routing.model_rank("gpt-5.5") is None


def test_missing_yaml_raises(tmp_path):
    with pytest.raises(_routing.RoutingConfigError):
        _routing.effort_for_tier("medium", config=tmp_path / "absent.yaml")


def test_non_mapping_yaml_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a list\n")
    with pytest.raises(_routing.RoutingConfigError):
        _routing.codex_timeouts(config=bad)


def test_repo_yaml_exists_and_loads():
    assert REPO_YAML.exists()
    assert _routing.effort_for_tier("medium", config=REPO_YAML) == "medium"


# --- new tests for wrong-typed sections, timeout coercion, bool ranks ---


def test_empty_yaml_raises(tmp_path):
    """safe_load('') -> None, which is not a dict -> RoutingConfigError."""
    empty = tmp_path / "empty.yaml"
    empty.write_text("")
    with pytest.raises(_routing.RoutingConfigError):
        _routing.effort_for_tier("medium", config=empty)


def test_non_mapping_codex_section_raises_codex_timeouts(tmp_path):
    """`codex: oops` is a string, not a mapping -> RoutingConfigError."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("codex: oops\n")
    with pytest.raises(_routing.RoutingConfigError):
        _routing.codex_timeouts(config=bad)


def test_non_mapping_codex_section_raises_effort_for_tier(tmp_path):
    """`codex: oops` is a string, not a mapping -> RoutingConfigError."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("codex: oops\n")
    with pytest.raises(_routing.RoutingConfigError):
        _routing.effort_for_tier("medium", config=bad)


def test_non_mapping_agent_model_rank_raises(tmp_path):
    """`agent_model_rank: oops` is a string -> RoutingConfigError on model_rank."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("agent_model_rank: oops\n")
    with pytest.raises(_routing.RoutingConfigError):
        _routing.model_rank("opus", config=bad)


def test_timeout_string_raises(tmp_path):
    """`timeout_s: 240s` (string) -> RoutingConfigError."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("codex:\n  timeout_s: \"240s\"\n  retry_timeout_s: 180\n")
    with pytest.raises(_routing.RoutingConfigError):
        _routing.codex_timeouts(config=bad)


def test_timeout_bool_raises(tmp_path):
    """`timeout_s: true` should be rejected -> RoutingConfigError."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("codex:\n  timeout_s: true\n  retry_timeout_s: 180\n")
    with pytest.raises(_routing.RoutingConfigError):
        _routing.codex_timeouts(config=bad)


def test_timeout_explicit_null_uses_defaults(tmp_path):
    """`timeout_s: null` (explicit None) -> fallback to (240, 180)."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("codex:\n  timeout_s:\n  retry_timeout_s:\n")
    timeout_s, retry_s = _routing.codex_timeouts(config=cfg)
    assert timeout_s == 240
    assert retry_s == 180


def test_bool_rank_returns_none(tmp_path):
    """`opus: true` — bool is not a valid rank integer -> model_rank returns None."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("agent_model_rank:\n  opus: true\n")
    assert _routing.model_rank("opus", config=cfg) is None


def test_verifier_min_tier_explicit_null_returns_opus(tmp_path):
    """`verifier_min_tier:` (null) -> default 'opus'."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("verifier_min_tier:\n")
    assert _routing.verifier_min_tier(config=cfg) == "opus"


# --- verifier_agents ---


def test_verifier_agents_from_repo_yaml():
    agents = _routing.verifier_agents()
    assert isinstance(agents, frozenset)
    assert "auto-pilot-codex-reviewer" in agents
    assert "auto-pilot-claude-reviewer" in agents
    assert "review-gatekeeper" in agents
    assert "swarm-verifier" in agents
    assert "tech-critic-lead" in agents
    assert len(agents) == 5


def test_verifier_agents_missing_key_raises(tmp_path):
    """yaml without verifier_agents: key -> RoutingConfigError (fail-closed)."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("verifier_min_tier: opus\nagent_model_rank:\n  opus: 1\n")
    with pytest.raises(_routing.RoutingConfigError, match="verifier_agents"):
        _routing.verifier_agents(config=cfg)


def test_verifier_agents_non_list_raises(tmp_path):
    """`verifier_agents: not-a-list` -> RoutingConfigError."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("verifier_agents: some-string\n")
    with pytest.raises(_routing.RoutingConfigError, match="verifier_agents"):
        _routing.verifier_agents(config=cfg)


def test_verifier_agents_non_string_entry_raises(tmp_path):
    """A non-string entry in verifier_agents -> RoutingConfigError."""
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("verifier_agents:\n  - valid-agent\n  - 42\n")
    with pytest.raises(_routing.RoutingConfigError, match="verifier_agents"):
        _routing.verifier_agents(config=cfg)
