from pathlib import Path

from evals._types import OracleResult, RunResult


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
