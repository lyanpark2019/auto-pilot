from __future__ import annotations

import json
from pathlib import Path
from unittest import mock


def test_run_case_sequence_and_teardown(tmp_path: Path) -> None:
    from evals import runner
    from evals._types import OracleResult

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(cmd if isinstance(cmd, list) else [cmd])
        return mock.Mock(returncode=0, stdout="", stderr="")

    teardown_seen: list[Path] = []

    with mock.patch("evals.runner.shutil.disk_usage",
                    return_value=mock.Mock(free=500 * 10**9)), \
        mock.patch("evals.runner.subprocess.run", side_effect=fake_run), \
        mock.patch("evals.runner.tempfile.mkdtemp", return_value=str(tmp_path / "clone")), \
        mock.patch("evals.runner._read_run_result",
                   return_value=mock.Mock(status="success", cost_usd=0.0)), \
        mock.patch("evals.runner.load_case_oracle",
                   return_value=lambda wd, rr: OracleResult("pass", "")), \
        mock.patch("evals.runner._teardown",
                   side_effect=lambda p: teardown_seen.append(p)):
        att = runner.run_case("dogfood-smoke", repo=tmp_path, run_id="r1")

    assert att.oracle.outcome == "pass"
    joined = " ".join(" ".join(c) for c in calls)
    assert "clone" in joined and "--local" in joined
    assert "orchestrator.py" in joined and "--spec" in joined and "--force" in joined
    assert "headless-loop.py" in joined
    assert len(calls) == 3
    assert calls[0][1] == "clone"
    assert calls[1][1].endswith("orchestrator.py")
    assert calls[2][1].endswith("headless-loop.py")
    assert len(teardown_seen) == 1


def test_run_case_teardown_on_failure(tmp_path: Path) -> None:
    from evals import runner

    teardown_seen: list[Path] = []
    with mock.patch("evals.runner.shutil.disk_usage",
                    return_value=mock.Mock(free=500 * 10**9)), \
        mock.patch("evals.runner.tempfile.mkdtemp", return_value=str(tmp_path / "clone")), \
        mock.patch("evals.runner.subprocess.run", side_effect=RuntimeError("boom")), \
        mock.patch("evals.runner._teardown",
                   side_effect=lambda p: teardown_seen.append(p)):
        att = runner.run_case("dogfood-smoke", repo=tmp_path, run_id="r1")

    assert att.oracle.outcome == "error"
    assert att.run.cost_usd == 0.0  # error attempt carries a zero-cost RunResult
    assert len(teardown_seen) == 1


def test_run_case_passes_uncapped_concurrency(tmp_path: Path) -> None:
    from evals import runner
    from evals._types import OracleResult

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(cmd if isinstance(cmd, list) else [cmd])
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch("evals.runner.shutil.disk_usage",
                    return_value=mock.Mock(free=500 * 10**9)), \
        mock.patch("evals.runner.subprocess.run", side_effect=fake_run), \
        mock.patch("evals.runner.tempfile.mkdtemp", return_value=str(tmp_path / "clone")), \
        mock.patch("evals.runner._read_run_result",
                   return_value=mock.Mock(status="success", cost_usd=0.0)), \
        mock.patch("evals.runner.load_case_oracle",
                   return_value=lambda wd, rr: OracleResult("pass", "")), \
        mock.patch("evals.runner._teardown"):
        runner.run_case("dogfood-smoke", repo=tmp_path)

    loop_cmd = next(c for c in calls if any("headless-loop.py" in part for part in c))
    assert "--max-concurrent-claude" in loop_cmd
    i = loop_cmd.index("--max-concurrent-claude")
    assert int(loop_cmd[i + 1]) >= 1000  # fork-bomb guard effectively disabled for the eval


def test_run_case_insufficient_disk_errors_without_cloning(tmp_path: Path) -> None:
    from evals import runner

    ran: list[str] = []
    with mock.patch("evals.runner.shutil.disk_usage",
                    return_value=mock.Mock(free=1 * 10**9)), \
        mock.patch("evals.runner.subprocess.run",
                   side_effect=lambda *a, **k: ran.append("ran")), \
        mock.patch("evals.runner.tempfile.mkdtemp",
                   side_effect=AssertionError("must not clone")):
        att = runner.run_case("dogfood-smoke", repo=tmp_path, min_free_disk_gb=2.0)

    assert att.oracle.outcome == "error"
    assert "disk" in att.oracle.reason.lower()
    assert ran == []  # no clone/init/loop ran


def test_read_run_result_reads_real_cost(tmp_path: Path) -> None:
    from evals import runner

    clone = tmp_path / "clone"
    state = clone / ".planning" / "auto-pilot" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"status": "success", "iter": 2, "cost_usd": 3.25}))
    rr = runner._read_run_result(clone)
    assert rr.cost_usd == 3.25
    assert rr.status == "success"
    assert rr.iters == 2
