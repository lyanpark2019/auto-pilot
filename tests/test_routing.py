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
