"""Narrow resolver over skills/auto-pilot/references/model-routing.yaml.

v1 is deliberately minimal (YAGNI): codex effort lookup, effort downgrade,
codex timeout budgets, verifier tier floor, and the verifier agent name set.
No role-x-task dispatch resolver — slice C's rebalance consumes structured
ledger records, not this module. Missing or invalid YAML raises
RoutingConfigError (fail-closed for library callers;
hooks/verifier-tier-gate.sh catches it and fails open so a config typo never
bricks all Task dispatch).
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


def _read(config: Path | None) -> tuple[Path, dict[str, Any]]:
    target = config if config is not None else ROUTING_YAML
    try:
        data = yaml.safe_load(target.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise RoutingConfigError(f"{target}: {exc}") from exc
    if not isinstance(data, dict):
        raise RoutingConfigError(
            f"{target}: expected mapping, got {type(data).__name__}"
        )
    return target, data


def _section(data: dict[str, Any], key: str, target: Path) -> dict[str, Any]:
    value = data.get(key) or {}
    if not isinstance(value, dict):
        raise RoutingConfigError(f"{target}: '{key}' must be a mapping")
    return value


def _timeout(section: dict[str, Any], key: str, default: int, target: Path) -> int:
    value = section.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoutingConfigError(
            f"{target}: '{key}' must be an integer (got {value!r})"
        )
    return int(value)


def effort_for_tier(tier: str, config: Path | None = None) -> str:
    """codex model_reasoning_effort for a risk_assess tier; unknown -> medium."""
    target, data = _read(config)
    codex = _section(data, "codex", target)
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
    target, data = _read(config)
    codex = _section(data, "codex", target)
    timeout_s = _timeout(codex, "timeout_s", 240, target)
    retry_s = _timeout(codex, "retry_timeout_s", 180, target)
    return timeout_s, retry_s


def verifier_min_tier(config: Path | None = None) -> str:
    """Agent-tool model token verifier dispatches must be at or above."""
    _, data = _read(config)
    return str(data.get("verifier_min_tier") or "opus")


def model_rank(token: str, config: Path | None = None) -> int | None:
    """Agent-tool model token -> tier rank (lower = higher); unknown -> None."""
    target, data = _read(config)
    ranks = _section(data, "agent_model_rank", target)
    value = ranks.get(token)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def verifier_agents(config: Path | None = None) -> frozenset[str]:
    """Subagent_type names subject to verifier-tier-gate enforcement.

    Reads the ``verifier_agents`` list from model-routing.yaml.
    Missing key, empty list, non-list value, or any non-string entry raises
    RoutingConfigError (fail-closed for library callers; the hook catches and
    fails open — a routing-config typo must never brick all Task dispatch).
    """
    target, data = _read(config)
    raw = data.get("verifier_agents")
    if raw is None:
        raise RoutingConfigError(
            f"{target}: 'verifier_agents' key is missing"
        )
    if not isinstance(raw, list):
        raise RoutingConfigError(
            f"{target}: 'verifier_agents' must be a list, got {type(raw).__name__}"
        )
    for item in raw:
        if not isinstance(item, str):
            raise RoutingConfigError(
                f"{target}: 'verifier_agents' entries must be strings, got {item!r}"
            )
    return frozenset(raw)
