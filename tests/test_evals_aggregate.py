from __future__ import annotations

import json
from pathlib import Path

from evals._types import OracleResult


def test_select_cases_by_tier(tmp_path: Path) -> None:
    from evals import aggregate

    cases = tmp_path / "cases"
    (cases / "a").mkdir(parents=True)
    (cases / "a" / "meta.json").write_text(json.dumps({"tags": ["smoke"]}))
    (cases / "b").mkdir()
    (cases / "b" / "meta.json").write_text(json.dumps({"tags": ["full"]}))

    assert aggregate.select_cases(cases, tier="smoke") == ["a"]
    assert sorted(aggregate.select_cases(cases, tier="full")) == ["a", "b"]


def test_aggregate_counts() -> None:
    from evals import aggregate

    results = [
        OracleResult("pass", ""),
        OracleResult("pass", ""),
        OracleResult("fail", "x"),
        OracleResult("error", "boom"),
    ]
    summary = aggregate.summarize("dogfood-smoke", results)
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["errored"] == 1
    assert summary["attempts"] == 4  # error counts toward total_attempted


def test_write_results_round_trip(tmp_path: Path) -> None:
    from evals import aggregate

    out = tmp_path / "results" / "run.json"  # parent dir does not exist yet
    aggregate.write_results(out, "r1", [{"case": "x", "passed": 1}])
    data = json.loads(out.read_text())
    assert data["run_id"] == "r1"
    assert data["cases"][0]["case"] == "x"


def test_cli_run_smoke_invokes_runner(tmp_path, monkeypatch, capsys):  # type: ignore[no-untyped-def]
    from evals import cli
    from evals._types import OracleResult

    # Hermetic: don't depend on the real evals/baseline.json contents.
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"cases": {"dogfood-smoke": {"passed": 5, "attempts": 5, "errored": 0}}})
    )
    monkeypatch.setattr("evals.cli._BASELINE", baseline)
    monkeypatch.setattr(
        "evals.cli.run_case",
        lambda case_id, **kw: OracleResult("pass", ""),
    )
    monkeypatch.setattr("evals.cli.select_cases", lambda d, tier: ["dogfood-smoke"])

    out_path = tmp_path / "r.json"
    rc = cli.main(["run", "--tier", "smoke", "--repeats", "1", "--out", str(out_path)])
    assert rc == 0  # cut-1 advisory: always exit 0
    out = capsys.readouterr().out
    assert "dogfood-smoke" in out
    assert out_path.exists()  # results JSON was written
