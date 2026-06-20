"""Pure statistics helpers for the learning-loop A/B driver (Task 10).

No third-party stats dependency — Fisher exact (one-sided), McNemar (exact
binomial on the discordant pairs), and a paired catch-rate delta with a 95%
confidence interval are computed from stdlib ``math`` only, so the verdict is
byte-reproducible on any host the eval harness runs on.

All inputs are paired binary outcomes: ``on`` and ``off`` are equal-length
sequences of 0/1 (caught/missed) over the SAME ordered set of scored stage-B
diffs.  The 2x2 table the Fisher test consumes is the catch/miss contingency,
NOT the paired discordance table (McNemar owns the paired axis).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PairedOutcome:
    """Counts derived from paired ON/OFF binary outcomes.

    ``b`` = ON caught & OFF missed (the effect direction we want).
    ``c`` = ON missed & OFF caught (the adverse direction).
    ``a`` / ``d`` = concordant (both caught / both missed) — McNemar ignores them.
    """

    a: int  # both caught
    b: int  # ON caught, OFF missed
    c: int  # ON missed, OFF caught
    d: int  # both missed

    @property
    def n(self) -> int:
        return self.a + self.b + self.c + self.d

    @property
    def discordant(self) -> int:
        return self.b + self.c


def paired_table(on: list[int], off: list[int]) -> PairedOutcome:
    """Build the 2x2 paired-outcome table from equal-length 0/1 sequences."""
    if len(on) != len(off):
        raise ValueError(f"paired sequences differ in length: {len(on)} vs {len(off)}")
    a = b = c = d = 0
    for o, f in zip(on, off):
        on_hit = bool(o)
        off_hit = bool(f)
        if on_hit and off_hit:
            a += 1
        elif on_hit and not off_hit:
            b += 1
        elif (not on_hit) and off_hit:
            c += 1
        else:
            d += 1
    return PairedOutcome(a=a, b=b, c=c, d=d)


def _log_factorial(n: int) -> float:
    """``ln(n!)`` via ``lgamma`` (stable for the table sizes a PoC reaches)."""
    return math.lgamma(n + 1)


def _hypergeom_logpmf(a: int, row1: int, row2: int, col1: int) -> float:
    """log P(top-left cell == a) under the hypergeometric (fixed margins)."""
    total = row1 + row2
    b = row1 - a
    c = col1 - a
    d = row2 - c
    if a < 0 or b < 0 or c < 0 or d < 0:
        return float("-inf")
    return (
        _log_factorial(row1) + _log_factorial(row2)
        + _log_factorial(col1) + _log_factorial(total - col1)
        - _log_factorial(total)
        - _log_factorial(a) - _log_factorial(b)
        - _log_factorial(c) - _log_factorial(d)
    )


def fisher_exact_one_sided(table: list[list[int]]) -> float:
    """One-sided Fisher exact p-value for a 2x2 table ``[[a,b],[c,d]]``.

    Tests the alternative that the top-left cell (``a``) is LARGER than chance —
    i.e. the ON arm's catch rate exceeds the OFF arm's.  Sums hypergeometric
    PMF over all tables with the same margins whose top-left cell is >= the
    observed ``a``.
    """
    (a, b), (c, d) = table
    row1 = a + b
    row2 = c + d
    col1 = a + c
    a_min = max(0, col1 - row2)
    a_max = min(row1, col1)
    observed = a
    log_p_obs = _hypergeom_logpmf(observed, row1, row2, col1)
    total = 0.0
    for ai in range(a_min, a_max + 1):
        if ai < observed:
            continue
        lp = _hypergeom_logpmf(ai, row1, row2, col1)
        if lp == float("-inf"):
            continue
        # Guard tiny float drift at the observed cell.
        if ai == observed:
            total += math.exp(log_p_obs)
        else:
            total += math.exp(lp)
    return min(1.0, total)


def _binom_cdf_upper(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) for X~Binomial(n, p) — used by the exact McNemar test."""
    if n == 0:
        return 1.0
    total = 0.0
    for i in range(k, n + 1):
        log_c = _log_factorial(n) - _log_factorial(i) - _log_factorial(n - i)
        total += math.exp(log_c + i * math.log(p) + (n - i) * math.log(1 - p))
    return min(1.0, total)


def mcnemar_exact(table: PairedOutcome, one_sided: bool = True) -> float:
    """Exact McNemar p-value on the discordant pairs (binomial, p=0.5).

    One-sided alternative: ON catches strictly more discordant pairs than OFF
    (``b > c``).  With zero discordant pairs the test is undefined → returns 1.0
    (no evidence of difference).
    """
    n = table.discordant
    if n == 0:
        return 1.0
    k = table.b
    p_upper = _binom_cdf_upper(k, n, 0.5)
    if one_sided:
        return p_upper
    return min(1.0, 2.0 * min(p_upper, _binom_cdf_upper(n - k, n, 0.5)))


@dataclass(frozen=True)
class DeltaCI:
    """Paired catch-rate delta and its 95% confidence interval."""

    catch_rate_on: float
    catch_rate_off: float
    delta: float
    ci_low: float
    ci_high: float


_Z_95 = 1.959963984540054  # two-sided 95% normal quantile


def catch_rate_delta_ci(on: list[int], off: list[int]) -> DeltaCI:
    """Paired catch-rate delta (ON - OFF) with a 95% CI.

    The CI uses the standard error of the paired difference of proportions
    (the per-pair difference ``on_i - off_i`` has values in {-1,0,1}); this is
    the McNemar-consistent paired SE, narrower than treating the arms as
    independent.  With n==0 the interval collapses to (0,0,0).
    """
    n = len(on)
    if n != len(off):
        raise ValueError("paired sequences differ in length")
    if n == 0:
        return DeltaCI(0.0, 0.0, 0.0, 0.0, 0.0)
    rate_on = sum(on) / n
    rate_off = sum(off) / n
    diffs = [on[i] - off[i] for i in range(n)]
    mean_diff = sum(diffs) / n
    if n == 1:
        return DeltaCI(rate_on, rate_off, mean_diff, mean_diff, mean_diff)
    var = sum((d - mean_diff) ** 2 for d in diffs) / (n - 1)
    se = math.sqrt(var / n)
    half = _Z_95 * se
    return DeltaCI(
        catch_rate_on=rate_on,
        catch_rate_off=rate_off,
        delta=mean_diff,
        ci_low=mean_diff - half,
        ci_high=mean_diff + half,
    )
