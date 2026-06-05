from __future__ import annotations

from pathlib import Path

from evals._types import RunResult

FIXTURES = Path(__file__).resolve().parent.parent / "evals" / "_fixtures"


def _run_result(workdir: Path) -> RunResult:
    return RunResult(
        returncode=0,
        status="success",
        state_path=workdir / ".planning/auto-pilot/state.json",
        cost_usd=0.0,
        iters=1,
        log_dir=workdir,
        workdir=workdir,
    )


def test_oracle_passes_good_fixture() -> None:
    from evals.oracle_api import load_case_oracle

    check = load_case_oracle("dogfood-smoke")
    good = FIXTURES / "good"
    res = check(good, _run_result(good))
    assert res.outcome == "pass", res.reason


def test_oracle_fails_broken_fixture() -> None:
    from evals.oracle_api import load_case_oracle

    check = load_case_oracle("dogfood-smoke")
    broken = FIXTURES / "broken"
    res = check(broken, _run_result(broken))
    assert res.outcome == "fail", res.reason


def test_load_case_oracle_missing_raises_importerror() -> None:
    import pytest

    from evals.oracle_api import load_case_oracle

    with pytest.raises(ImportError):
        load_case_oracle("nonexistent-case")
