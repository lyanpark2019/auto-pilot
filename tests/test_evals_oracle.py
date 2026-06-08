from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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


def test_run_verify_cmd_uses_argv_not_shell(tmp_path: Path) -> None:
    import subprocess

    from evals.oracle_api import run_verify_cmd

    completed = subprocess.CompletedProcess(["python3"], 0, "ok", "")
    with patch("evals.oracle_api.subprocess.run", return_value=completed) as run:
        ok, detail = run_verify_cmd(tmp_path, 'python3 -c "print(1)"')

    assert ok is True
    assert detail == "ok"
    assert run.call_args.args[0] == ["python3", "-c", "print(1)"]
    assert "shell" not in run.call_args.kwargs
    assert run.call_args.kwargs["timeout"] == 120


def test_load_case_oracle_missing_raises_importerror() -> None:
    import pytest

    from evals.oracle_api import load_case_oracle

    with pytest.raises(ImportError):
        load_case_oracle("nonexistent-case")
