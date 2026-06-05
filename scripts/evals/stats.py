"""Deterministic regression statistics — stdlib only (no scipy/numpy).

Newcombe (method-10) confidence interval for the difference of two proportions,
each estimated by a Wilson score interval. Used by regress.py. The gate fires
when the upper bound of (p_new - p_base) drops below -margin: i.e. we are
confident the new run is worse by more than the margin.
"""
from __future__ import annotations

import math

Z95 = 1.96  # two-sided 95%
DEFAULT_MARGIN = 0.05
DEFAULT_ARM_MIN = 50


def _wilson(x: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval ``(lower, upper)`` for x successes in n trials."""
    if n == 0:
        return (0.0, 1.0)
    p = x / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (center - half, center + half)


def diff_upper(
    x_new: int, n_new: int, x_base: int, n_base: int, z: float = Z95
) -> float:
    """Newcombe method-10 upper bound of ``(p_new - p_base)``."""
    p1, p2 = x_new / n_new, x_base / n_base
    _, u1 = _wilson(x_new, n_new, z)
    l2, _ = _wilson(x_base, n_base, z)
    return (p1 - p2) + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def is_regression(
    x_new: int,
    n_new: int,
    x_base: int,
    n_base: int,
    margin: float = DEFAULT_MARGIN,
    arm_min: int = DEFAULT_ARM_MIN,
) -> tuple[bool, bool]:
    """Return ``(armed, failed)``.

    ``armed`` is False (advisory) when ``n_new < arm_min``; ``failed`` can only be
    True when armed. A run is a regression when the difference-interval upper bound
    is below ``-margin``.
    """
    armed = n_new >= arm_min
    failed = armed and diff_upper(x_new, n_new, x_base, n_base) < -margin
    return armed, failed
