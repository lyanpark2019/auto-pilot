"""Compare an eval run against a blessed baseline.

CUT 1: advisory by construction — ``blocking`` is always False (the rate gate
arms in cut 2). We still compute ``would_fire`` so the advisory report is honest.
"""
from __future__ import annotations

from typing import Any

from evals.stats import is_regression


def compare(
    new: dict[str, Any],
    baseline: dict[str, Any],
    margin: float = 0.05,
    cut1: bool = True,
) -> dict[str, Any]:
    """Compare run summary ``new`` to ``baseline``.

    Returns a dict with keys ``armed`` / ``would_fire`` / ``error_spike`` / ``blocking``.
    In cut 1 ``blocking`` is always False (advisory).
    """
    armed, failed = is_regression(
        new["passed"], new["attempts"],
        baseline["passed"], baseline["attempts"],
        margin=margin,
    )
    # errored is optional in the summary schema; passed/attempts are required
    # (a missing passed/attempts is a malformed summary, not a zero default).
    error_spike = new.get("errored", 0) > baseline.get("errored", 0)
    would_fire = bool(failed or error_spike)
    blocking = False if cut1 else (armed and would_fire)
    return {
        "armed": armed,
        "would_fire": would_fire,
        "error_spike": error_spike,
        "blocking": blocking,
    }
