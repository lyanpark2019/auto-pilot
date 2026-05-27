"""Performance baseline for orchestrator CLI commands.

Budget: each command must complete in <50ms (cold), <5ms (warm).
Run with: pytest tests/test_perf.py --benchmark-only
"""
from __future__ import annotations

import pytest

import orchestrator  # type: ignore[import-not-found]


BUDGET_MS = 50.0  # per-command ceiling


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
    assert benchmark.stats["mean"] * 1000 < BUDGET_MS, (
        f"cmd_status exceeded {BUDGET_MS}ms budget"
    )


def test_phase_start_within_budget(benchmark, initialized_state, capsys):
    def _run():
        orchestrator.main(["phase-start", "--phase", "1", "--contracts", "3"])
        capsys.readouterr()

    benchmark.pedantic(_run, rounds=20, warmup_rounds=2)
    assert benchmark.stats["mean"] * 1000 < BUDGET_MS, (
        f"cmd_phase_start exceeded {BUDGET_MS}ms budget"
    )


def test_phase_end_within_budget(benchmark, initialized_state, capsys):
    orchestrator.main(["phase-start", "--phase", "1", "--contracts", "1"])

    def _run():
        orchestrator.main(
            ["phase-end", "--phase", "1", "--status", "success", "--commits", "abc"]
        )
        capsys.readouterr()

    benchmark.pedantic(_run, rounds=20, warmup_rounds=2)
    assert benchmark.stats["mean"] * 1000 < BUDGET_MS, (
        f"cmd_phase_end exceeded {BUDGET_MS}ms budget"
    )
