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
