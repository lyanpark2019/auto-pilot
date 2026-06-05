from __future__ import annotations

from evals.regress import compare


def test_compare_advisory_below_arm_floor() -> None:
    # cut-1: 1 case * K=5 = 5 attempts, below arm floor -> advisory, blocking False
    verdict = compare(
        new={"passed": 4, "attempts": 5, "errored": 0},
        baseline={"passed": 1000, "attempts": 1000, "errored": 0},
        cut1=True,
    )
    assert verdict["armed"] is False
    assert verdict["blocking"] is False  # cut-1 never blocks


def test_compare_reports_regression_advisory_even_when_would_fire() -> None:
    verdict = compare(
        new={"passed": 40, "attempts": 50, "errored": 0},
        baseline={"passed": 1000, "attempts": 1000, "errored": 0},
        cut1=True,
    )
    assert verdict["would_fire"] is True   # statistically a drop
    assert verdict["blocking"] is False    # but cut-1 is advisory by construction


def test_compare_error_spike_sets_would_fire() -> None:
    # error_spike is the OTHER way would_fire becomes True (not just a rate drop)
    verdict = compare(
        new={"passed": 5, "attempts": 5, "errored": 2},
        baseline={"passed": 5, "attempts": 5, "errored": 0},
        cut1=True,
    )
    assert verdict["error_spike"] is True
    assert verdict["would_fire"] is True
    assert verdict["blocking"] is False  # cut-1 still advisory


def test_compare_cut2_blocks_when_armed_and_would_fire() -> None:
    # the cut1=False branch is the cut-2 gate; lock its semantics in now
    verdict = compare(
        new={"passed": 40, "attempts": 50, "errored": 0},
        baseline={"passed": 1000, "attempts": 1000, "errored": 0},
        cut1=False,
    )
    assert verdict["armed"] is True
    assert verdict["would_fire"] is True
    assert verdict["blocking"] is True
