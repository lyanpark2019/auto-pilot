"""Central config for auto-pilot scripts. Stdlib only."""
from __future__ import annotations
import os
import shutil
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AutoPilotConfig:
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


def load() -> AutoPilotConfig:
    """Resolve config from env vars with documented defaults."""
    claude_bin = (
        os.environ.get("CLAUDE_BIN")
        or shutil.which("claude")
        or "claude"
    )
    return AutoPilotConfig(claude_bin=claude_bin)
