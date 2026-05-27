"""Performance baseline for orchestrator CLI commands.

Two-layer gate per test:
  1. Absolute budget: mean < 50ms (the hard ceiling).
  2. Regression gate: mean <= committed baseline (tests/perf_baseline.json).

Run with: pytest tests/test_perf.py --benchmark-only
Baseline refresh procedure: see docs/perf-budget.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import orchestrator  # type: ignore[import-not-found]


BUDGET_MS = 50.0  # per-command ceiling
BASELINE_PATH = Path(__file__).parent / "perf_baseline.json"


def _baseline_mean(fullname: str) -> float:
    """Return committed baseline mean (seconds) for a benchmark fullname suffix."""
    data = json.loads(BASELINE_PATH.read_text())
    for entry in data["benchmarks"]:
        if entry["fullname"].endswith(fullname):
            return float(entry["stats"]["mean"])
    raise KeyError(f"no baseline for {fullname}")


@pytest.fixture()
def initialized_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "spec.md"
    spec.write_text("## Phase 1\n## Phase 2\n## Phase 3\n")
    orchestrator.main(["init", "--spec", str(spec)])
    return tmp_path


def test_status_within_budget(benchmark, initialized_state, capsys):
    def _run():
        orchestrator.main(["status"])
        capsys.readouterr()  # drain to avoid memory growth

    benchmark(_run)
    mean = benchmark.stats["mean"]
    assert mean * 1000 < BUDGET_MS, f"cmd_status exceeded {BUDGET_MS}ms budget"
    baseline = _baseline_mean("test_status_within_budget")
    assert mean <= baseline, (
        f"perf regression: {mean*1000:.3f}ms > baseline {baseline*1000:.3f}ms"
    )


def test_phase_start_within_budget(benchmark, initialized_state, capsys):
    def _run():
        orchestrator.main(["phase-start", "--phase", "1", "--contracts", "3"])
        capsys.readouterr()

    benchmark.pedantic(_run, rounds=20, warmup_rounds=2)
    mean = benchmark.stats["mean"]
    assert mean * 1000 < BUDGET_MS, f"cmd_phase_start exceeded {BUDGET_MS}ms budget"
    baseline = _baseline_mean("test_phase_start_within_budget")
    assert mean <= baseline, (
        f"perf regression: {mean*1000:.3f}ms > baseline {baseline*1000:.3f}ms"
    )


def test_phase_end_within_budget(benchmark, initialized_state, capsys):
    orchestrator.main(["phase-start", "--phase", "1", "--contracts", "1"])

    def _run():
        orchestrator.main(
            ["phase-end", "--phase", "1", "--status", "success", "--commits", "abc"]
        )
        capsys.readouterr()

    benchmark.pedantic(_run, rounds=20, warmup_rounds=2)
    mean = benchmark.stats["mean"]
    assert mean * 1000 < BUDGET_MS, f"cmd_phase_end exceeded {BUDGET_MS}ms budget"
    baseline = _baseline_mean("test_phase_end_within_budget")
    assert mean <= baseline, (
        f"perf regression: {mean*1000:.3f}ms > baseline {baseline*1000:.3f}ms"
    )
