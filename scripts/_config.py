"""Central config for auto-pilot scripts. Stdlib only."""
from __future__ import annotations
import os
import shutil
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AutoPilotConfig:
    """Represent AutoPilotConfig data for this module."""
    claude_bin: str
    headless_env: dict[str, str] = field(default_factory=lambda: {
        "HARNESS_HEADLESS": "1",
        "AUTO_PILOT_HEADLESS": "1",
    })
    default_max_iter: int = 100
    default_sleep_sec: int = 10
    default_timeout_build_sec: int = 4 * 3600
    default_max_cost_usd: float = 50.0
    default_max_tokens: int = 50_000_000
    default_per_iter_cost_estimate_usd: float = 0.50
    default_max_concurrent_claude: int = 4
    monitored_ports: tuple[int, ...] = (8000, 3000, 5000, 8080)
    # Preflight artifact max age; mirrors PREFLIGHT_TTL_SEC in _dispatch.py.
    # Env var: AUTO_PILOT_PREFLIGHT_TTL_SEC (same name as the dispatch module reads).
    preflight_ttl_sec: int = 900

    def __post_init__(self) -> None:
        # headless-loop.py: range(1, max_iter + 1) — zero or negative is nonsensical
        _check_int_bounds("default_max_iter", self.default_max_iter, ge=1, le=10_000)
        # time.sleep(args.sleep) — zero causes busy-spin; 1 h is a generous upper cap
        _check_int_bounds("default_sleep_sec", self.default_sleep_sec, ge=1, le=3_600)
        # threading.Timer(timeout_sec, …) — must be positive; 24 h covers any build
        _check_float_bounds("default_timeout_build_sec", self.default_timeout_build_sec, gt=0, le=86_400)
        # _budget.check_caps: cost > args.max_cost_usd — must be positive; $10k is a hard ceiling
        _check_float_bounds("default_max_cost_usd", self.default_max_cost_usd, gt=0, le=10_000)
        # _budget.check_caps: tokens > args.max_tokens — must be at least 1
        _check_int_bounds("default_max_tokens", self.default_max_tokens, ge=1, le=1_000_000_000)
        # fallback per-iter cost substituted when log has no total — must be positive
        _check_float_bounds("default_per_iter_cost_estimate_usd", self.default_per_iter_cost_estimate_usd, gt=0, le=1_000)
        # _budget.check_caps: pid growth over startup baseline >= cap — at least 1 allowed
        _check_int_bounds("default_max_concurrent_claude", self.default_max_concurrent_claude, ge=1, le=64)
        # _dispatch.py: age_sec > PREFLIGHT_TTL_SEC — 60 s minimum to avoid instant expiry
        _check_int_bounds("preflight_ttl_sec", self.preflight_ttl_sec, ge=60, le=86_400)


def _check_int_bounds(name: str, value: int, ge: int | None = None, le: int | None = None) -> None:
    if ge is not None and value < ge:
        raise ValueError(f"{name}={value!r} is out of range: must be >= {ge}")
    if le is not None and value > le:
        raise ValueError(f"{name}={value!r} is out of range: must be <= {le}")


def _check_float_bounds(
    name: str, value: float, gt: float | None = None, le: float | None = None
) -> None:
    if gt is not None and value <= gt:
        raise ValueError(f"{name}={value!r} is out of range: must be > {gt}")
    if le is not None and value > le:
        raise ValueError(f"{name}={value!r} is out of range: must be <= {le}")


PREFLIGHT_TTL_DEFAULT = 900
PREFLIGHT_TTL_MIN = 60
PREFLIGHT_TTL_MAX = 86_400


def preflight_ttl_sec() -> int:
    """Resolve AUTO_PILOT_PREFLIGHT_TTL_SEC, fail-soft to default if invalid."""
    raw = os.environ.get("AUTO_PILOT_PREFLIGHT_TTL_SEC")
    if raw is None:
        return PREFLIGHT_TTL_DEFAULT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return PREFLIGHT_TTL_DEFAULT
    if value < PREFLIGHT_TTL_MIN or value > PREFLIGHT_TTL_MAX:
        return PREFLIGHT_TTL_DEFAULT
    return value


def load() -> AutoPilotConfig:
    """Resolve config from env vars with documented defaults."""
    claude_bin = (
        os.environ.get("CLAUDE_BIN")
        or shutil.which("claude")
        or "claude"
    )
    return AutoPilotConfig(claude_bin=claude_bin, preflight_ttl_sec=preflight_ttl_sec())
