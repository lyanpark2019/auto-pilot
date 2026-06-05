from __future__ import annotations

from pathlib import Path
from unittest import mock

from evals._types import OracleResult


def test_run_case_sequence_and_teardown(tmp_path: Path) -> None:
    from evals import runner

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(cmd if isinstance(cmd, list) else [cmd])
        return mock.Mock(returncode=0, stdout="", stderr="")

    teardown_seen: list[Path] = []

    with mock.patch("evals.runner.subprocess.run", side_effect=fake_run), \
        mock.patch(
            "evals.runner._read_run_result",
            return_value=mock.Mock(status="success"),
        ), \
        mock.patch(
            "evals.runner.load_case_oracle",
            return_value=lambda wd, rr: OracleResult("pass", ""),
        ), \
        mock.patch(
            "evals.runner._teardown",
            side_effect=lambda p: teardown_seen.append(p),
        ), \
        mock.patch(
            "evals.runner.tempfile.mkdtemp",
            return_value=str(tmp_path / "clone"),
        ):
        res = runner.run_case("dogfood-smoke", repo=tmp_path, run_id="r1")

    assert res.outcome == "pass"
    # clone, then orchestrator init --spec --force, then headless-loop ran
    joined = " ".join(" ".join(c) for c in calls)
    assert "clone" in joined and "--local" in joined
    assert "orchestrator.py" in joined and "--spec" in joined and "--force" in joined
    assert "headless-loop.py" in joined
    assert len(teardown_seen) == 1  # teardown fired exactly once
    assert len(calls) == 3
    assert calls[0][1] == "clone"                       # git clone first
    assert calls[1][1].endswith("orchestrator.py")      # then init
    assert calls[2][1].endswith("headless-loop.py")     # then the loop


def test_run_case_teardown_on_failure(tmp_path: Path) -> None:
    from evals import runner

    teardown_seen: list[Path] = []
    with mock.patch(
        "evals.runner.subprocess.run",
        side_effect=RuntimeError("boom"),
    ), mock.patch(
        "evals.runner._teardown",
        side_effect=lambda p: teardown_seen.append(p),
    ), mock.patch(
        "evals.runner.tempfile.mkdtemp",
        return_value=str(tmp_path / "clone"),
    ):
        res = runner.run_case("dogfood-smoke", repo=tmp_path, run_id="r1")

    assert res.outcome == "error"
    assert len(teardown_seen) == 1  # teardown still fired on the failure path
