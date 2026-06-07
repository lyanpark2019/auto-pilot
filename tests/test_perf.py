"""Performance baseline for orchestrator CLI commands.

Two-layer gate per test:
  1. Absolute budget: mean < 50ms (the hard ceiling).
  2. Regression gate: mean <= committed baseline (tests/perf_baseline.json).

Run with: pytest tests/test_perf.py --benchmark-only
Baseline refresh procedure: see docs/perf-budget.md.
"""
from __future__ import annotations

import json
import resource
import sys
from pathlib import Path

import pytest

import orchestrator  # type: ignore[import-not-found]
import risk_assess  # type: ignore[import-not-found]


BUDGET_MS = 50.0  # per-command ceiling
BASELINE_PATH = Path(__file__).parent / "perf_baseline.json"

# Peak RSS ceiling for a representative hot-path call sequence (assess 200 paths).
# macOS reports ru_maxrss in bytes; Linux in KB. Ceiling is generous: 200 MB on
# macOS (200 * 1024 * 1024) or 200 MB as KB (200 * 1024).
_RSS_CEILING_BYTES_MACOS = 200 * 1024 * 1024
_RSS_CEILING_KB_LINUX = 200 * 1024


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


def test_pivot_check_within_budget(benchmark) -> None:
    """Benchmark the risk_assess hot path (pivot-check operation).

    assess() is called per finding within a review round — must stay well under
    50ms even for a realistic batch of 20 changed paths.
    """
    paths = [
        "scripts/_contract.py",
        "scripts/_dispatch.py",
        "scripts/risk_assess.py",
        "hooks/pre-bash-guard.sh",
        "hooks/branch-lock.sh",
        "schemas/contract.schema.json",
        "tests/test_contract.py",
        "docs/architecture.md",
        "skills/adversarial-review-loop/SKILL.md",
        "agents/worker.md",
        "agents/pm-orchestrator.md",
        "swarm/scripts/ticket_worker.py",
        ".claude-plugin/plugin.json",
        "hooks/gh-auth-preflight.sh",
        "scripts/_worktree.py",
        "scripts/_budget.py",
        "codex/worker-prompt.md",
        "vault/pipeline/build.py",
        "evals/harness.py",
        "dashboard/scorecard.json",
    ]

    benchmark(risk_assess.assess, paths)
    mean = benchmark.stats["mean"]
    assert mean * 1000 < BUDGET_MS, (
        f"pivot_check (risk_assess.assess) exceeded {BUDGET_MS}ms budget: "
        f"{mean * 1000:.3f}ms mean"
    )


def test_rss_under_ceiling() -> None:
    """Peak RSS of the process after a representative assess() call sequence.

    ru_maxrss semantics differ by OS:
      - macOS (Darwin): bytes
      - Linux: kilobytes

    Ceiling is 200 MB — generous enough to never flake, tight enough to catch
    a runaway allocation (e.g. reading a full 100KB fixture into memory per call).
    """
    # Warm up import caches before measuring
    paths = [
        "scripts/_contract.py",
        "scripts/risk_assess.py",
        "hooks/branch-lock.sh",
        "schemas/contract.schema.json",
        "tests/test_perf.py",
    ] * 40  # 200 paths total
    for _ in range(50):
        risk_assess.assess(paths)

    rss_raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        rss_mb = rss_raw / (1024 * 1024)
        ceiling_mb = _RSS_CEILING_BYTES_MACOS / (1024 * 1024)
    else:
        # Linux: ru_maxrss is KB
        rss_mb = rss_raw / 1024
        ceiling_mb = _RSS_CEILING_KB_LINUX / 1024

    assert rss_mb < ceiling_mb, (
        f"peak RSS {rss_mb:.1f} MB exceeds {ceiling_mb:.0f} MB ceiling"
    )
