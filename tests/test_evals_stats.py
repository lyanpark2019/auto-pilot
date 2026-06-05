from __future__ import annotations

from pathlib import Path

from evals._types import OracleResult, RunResult
from evals.stats import diff_upper, is_regression


def test_run_result_and_oracle_result_construct() -> None:
    rr = RunResult(
        returncode=0,
        status="success",
        state_path=Path(".planning/auto-pilot/state.json"),
        cost_usd=1.23,
        iters=2,
        log_dir=Path("/tmp/logs"),
        workdir=Path("/tmp/clone"),
    )
    assert rr.status == "success"
    ok = OracleResult(outcome="pass", reason="")
    assert ok.outcome == "pass"


def test_wilson_diff_upper_matches_reviewer_numbers() -> None:
    # regression: new 76/100 vs baseline 100/100 -> upper ~ -0.158 (fires)
    assert round(diff_upper(76, 100, 100, 100), 3) == -0.158
    # noise: 99/100 vs 100/100 -> upper ~ +0.028 (passes)
    assert diff_upper(99, 100, 100, 100) > -0.05
    # improvement: 100/100 vs 95/100 -> positive, never fires
    assert diff_upper(100, 100, 95, 100) > 0


def test_arming_and_mde_boundary() -> None:
    # below arm floor (A < 50): advisory regardless
    armed, failed = is_regression(0, 5, 1000, 1000)
    assert armed is False and failed is False
    # at A=50 with gated baseline ~1.0 (C*B*K = 1000): MDE boundary
    armed, failed = is_regression(44, 50, 1000, 1000)  # -0.056 < -0.05
    assert armed is True and failed is True
    armed, failed = is_regression(45, 50, 1000, 1000)  # -0.043 >= -0.05
    assert armed is True and failed is False
