"""Tests for cost_tracker: record/round_cost/total_cost/over_budget."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cost_tracker import CostTracker


def test_record_writes_jsonl(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    os.environ.pop("CLAUDE_PLUGIN_DATA", None)
    tr = CostTracker(vault)
    entry = tr.record(
        round_num=1,
        worker_type="vault-graph-enricher",
        usage={"input_tokens": 1_000_000, "output_tokens": 500_000},
        model="sonnet",
    )
    # sonnet: 1M*$3 + 0.5M*$15 = $3 + $7.5 = $10.5
    assert entry["cost_usd"] == pytest.approx(10.5, rel=1e-3)
    assert tr.log_path.exists()
    line = tr.log_path.read_text().strip()
    assert json.loads(line)["worker"] == "vault-graph-enricher"


def test_round_and_total_cost(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    tr = CostTracker(vault)
    tr.record(1, "a", {"input_tokens": 1_000_000}, model="sonnet")  # $3
    tr.record(1, "b", {"input_tokens": 1_000_000}, model="sonnet")  # $3
    tr.record(2, "c", {"input_tokens": 1_000_000}, model="sonnet")  # $3
    assert tr.round_cost(1) == pytest.approx(6.0)
    assert tr.round_cost(2) == pytest.approx(3.0)
    assert tr.total_cost() == pytest.approx(9.0)


def test_over_budget_round_cap(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    tr = CostTracker(vault)
    tr.mode = "api"
    tr.max_round_usd = 5.0
    tr.max_total_usd = 100.0
    tr.record(1, "w", {"input_tokens": 2_000_000}, model="sonnet")  # $6 > $5
    over, msg = tr.over_budget(1)
    assert over
    assert "round 1" in msg


def test_over_budget_total_cap(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    tr = CostTracker(vault)
    tr.mode = "api"
    tr.max_round_usd = 1000.0
    tr.max_total_usd = 5.0
    tr.record(1, "w", {"input_tokens": 2_000_000}, model="sonnet")  # $6
    over, msg = tr.over_budget(1)
    assert over
    assert "total" in msg


def test_subscription_mode_never_over_budget(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    tr = CostTracker(vault)
    tr.mode = "subscription"
    tr.max_round_usd = 0.01
    tr.max_total_usd = 0.01
    tr.record(1, "w", {"input_tokens": 10_000_000}, model="opus")  # huge $
    over, msg = tr.over_budget(1)
    assert not over
    assert "subscription" in msg.lower()


def test_report_aggregates(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    tr = CostTracker(vault)
    tr.record(1, "alpha", {"input_tokens": 1_000_000}, model="sonnet")
    tr.record(1, "beta", {"input_tokens": 1_000_000}, model="sonnet")
    tr.record(2, "alpha", {"input_tokens": 1_000_000}, model="sonnet")
    r = tr.report()
    assert r["per_worker"]["alpha"] == pytest.approx(6.0)
    assert r["per_round"][1] == pytest.approx(6.0)
    assert r["total_usd"] == pytest.approx(9.0)
