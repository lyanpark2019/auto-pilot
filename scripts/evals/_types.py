"""Value types handed to every case oracle. The one interface case authors touch."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Terminal state.json statuses (headless-loop.py:200). Non-"success" => non-pass.
TERMINAL_STATUSES = frozenset(
    {"success", "stopped", "pivot-needed", "failed", "cost-cap"}
)


@dataclass(frozen=True)
class RunResult:
    """What the runner produces per case attempt."""

    returncode: int  # headless-loop exit code (0 ok, 2 = no state, 124 = timeout)
    status: str  # final state.json status; one of TERMINAL_STATUSES
    state_path: Path  # the run's .planning/auto-pilot/state.json
    cost_usd: float  # best-effort (_budget.parse_session_usage; may be an estimate)
    iters: int
    log_dir: Path
    workdir: Path  # the case clone root


@dataclass(frozen=True)
class OracleResult:
    """Deterministic per-case verdict. outcome in {pass, fail, error}."""

    outcome: str
    reason: str  # required for fail/error; "" for pass
