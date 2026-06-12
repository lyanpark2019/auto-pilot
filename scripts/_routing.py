"""Narrow resolver over skills/auto-pilot/references/model-routing.yaml.

v1 is deliberately minimal (YAGNI): codex effort lookup, effort downgrade,
codex timeout budgets, and the verifier tier floor. No role-x-task dispatch
resolver — slice C's rebalance consumes structured ledger records, not this
module. Missing or invalid YAML raises RoutingConfigError (fail-closed for
library callers; hooks/verifier-tier-gate.sh catches it and fails open so a
config typo never bricks all Task dispatch).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROUTING_YAML = (
    Path(__file__).resolve().parent.parent
    / "skills" / "auto-pilot" / "references" / "model-routing.yaml"
)

_EFFORT_LADDER: tuple[str, ...] = ("low", "medium", "high", "xhigh")
_DEFAULT_EFFORT = "medium"


class RoutingConfigError(Exception):
    """model-routing.yaml is missing or structurally invalid."""


def _read(config: Path | None) -> dict[str, Any]:
    target = config if config is not None else ROUTING_YAML
    try:
        data = yaml.safe_load(target.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise RoutingConfigError(f"{target}: {exc}") from exc
    if not isinstance(data, dict):
        raise RoutingConfigError(
            f"{target}: expected mapping, got {type(data).__name__}"
        )
    return data


def effort_for_tier(tier: str, config: Path | None = None) -> str:
    """codex model_reasoning_effort for a risk_assess tier; unknown -> medium."""
    codex = _read(config).get("codex") or {}
    efforts = codex.get("effort_by_risk_tier") or {}
    effort = str(efforts.get(tier, _DEFAULT_EFFORT))
    return effort if effort in _EFFORT_LADDER else _DEFAULT_EFFORT


def lower_effort(effort: str) -> str:
    """One step down the codex effort ladder; floor (and unknown) -> low."""
    if effort not in _EFFORT_LADDER:
        return _EFFORT_LADDER[0]
    return _EFFORT_LADDER[max(_EFFORT_LADDER.index(effort) - 1, 0)]


def codex_timeouts(config: Path | None = None) -> tuple[int, int]:
    """(timeout_s, retry_timeout_s) budgets for the bounded codex invocation."""
    codex = _read(config).get("codex") or {}
    return int(codex.get("timeout_s", 240)), int(codex.get("retry_timeout_s", 180))


def verifier_min_tier(config: Path | None = None) -> str:
    """Agent-tool model token verifier dispatches must be at or above."""
    return str(_read(config).get("verifier_min_tier", "opus"))


def model_rank(token: str, config: Path | None = None) -> int | None:
    """Agent-tool model token -> tier rank (lower = higher); unknown -> None."""
    ranks = _read(config).get("agent_model_rank") or {}
    value = ranks.get(token)
    return int(value) if isinstance(value, int) else None
