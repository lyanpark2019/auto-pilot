"""Tests for pure helper functions in scripts/_rebalance.py.

Covers: normalize_model_token, _parse_ts timestamp edge cases, unknown-model
skipping, and the F2 end-to-end short-token normalisation path.

Rule-engine / arbitration scenario tests live in test_rebalance.py.

Shared helpers (seed_ledger, ledger_record) live in conftest.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _ledger  # noqa: E402
import _rebalance  # noqa: E402

from conftest import ledger_record as _record, seed_ledger as _seed_ledger  # noqa: E402

LADDER = ["fable", "opus", "sonnet", "haiku"]


# ---------------------------------------------------------------------------
# Unknown model
# ---------------------------------------------------------------------------

class TestUnknownModel:
    def test_unknown_model_skipped(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-narrow"] = {"model": "gpt-5.5"}
        ledger["records"] = [
            _record(f"t{i}", role="worker-narrow", task_class="narrow-port",
                    model="gpt-5.5", gates_first_try=False)
            for i in range(1, 3)
        ]
        assert not any(p["role"] == "worker-narrow"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))


# ---------------------------------------------------------------------------
# F2: model token normalisation — pure unit + end-to-end
# ---------------------------------------------------------------------------

class TestNormalizeModelToken:
    def test_short_token_maps_to_canonical(self) -> None:
        cladder = ["fable", "opus-4.8", "opus-4.6", "sonnet-4.6-1m", "haiku-4.5"]
        assert _rebalance.normalize_model_token("sonnet", cladder) == "sonnet-4.6-1m"
        assert _rebalance.normalize_model_token("haiku", cladder) == "haiku-4.5"
        assert _rebalance.normalize_model_token("gpt-5.5", cladder) == "gpt-5.5"

    def test_already_in_ladder_unchanged(self) -> None:
        cladder = ["fable", "opus-4.8", "opus-4.6", "sonnet-4.6-1m", "haiku-4.5"]
        assert _rebalance.normalize_model_token("fable", cladder) == "fable"
        assert _rebalance.normalize_model_token("sonnet-4.6-1m", cladder) == "sonnet-4.6-1m"

    def test_end_to_end_short_assignment_canonical_ladder(self) -> None:
        # F2: assignment short token normalised; rule fires against canonical ladder.
        cladder = ["fable", "opus-4.8", "opus-4.6", "sonnet-4.6-1m", "haiku-4.5"]
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record(f"t{i}", gates_first_try=False, task_class="feature-multi-file",
                    model="sonnet")
            for i in range(1, 3)
        ]
        assert any(p["rule"] == "promote-2x-gate-fail"
                   for p in _ledger.evaluate_rebalance(ledger, cladder))


# ---------------------------------------------------------------------------
# F-E: datetime ts comparison
# ---------------------------------------------------------------------------

class TestTimestampComparison:
    def test_plus09_offset_sorts_correctly_vs_utc(self) -> None:
        from _rebalance import _parse_ts
        assert _parse_ts("2026-06-12T10:00:00+09:00") == _parse_ts("2026-06-12T01:00:00+00:00")

    def test_fractional_seconds_parsed(self) -> None:
        from _rebalance import _parse_ts
        assert _parse_ts("2026-06-12T10:00:00.123456+00:00").microsecond == 123456

    def test_z_equals_plus00(self) -> None:
        from _rebalance import _parse_ts
        assert _parse_ts("2026-06-12T10:00:00Z") == _parse_ts("2026-06-12T10:00:00+00:00")

    def test_z_suffix_not_counted_as_fresh(self) -> None:
        # Z vs +00:00 at same instant: records at same ts as rebalance_log not fresh.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "opus"}
        ledger["records"] = [
            _record(f"t{i}", gates_first_try=False, task_class="feature-multi-file",
                    model="sonnet", ts="2026-06-12T10:00:00Z")
            for i in range(1, 3)
        ]
        ledger["rebalance_log"] = [{
            "ts": "2026-06-12T10:00:00+00:00",
            "role": "worker-primary", "task_class": "feature-multi-file",
            "from_model": "sonnet", "to_model": "opus",
            "rule": "promote-2x-gate-fail", "evidence": ["t1", "t2"],
        }]
        assert _ledger.evaluate_rebalance(ledger, LADDER) == []

    def test_offset_does_not_refire_on_consumed_evidence(self) -> None:
        # +09:00 equal to +00:00 in UTC — not fresh.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "opus"}
        ledger["records"] = [
            _record(f"t{i}", gates_first_try=False, task_class="feature-multi-file",
                    model="sonnet", ts="2026-06-12T10:00:00+09:00")
            for i in range(1, 3)
        ]
        ledger["rebalance_log"] = [{
            "ts": "2026-06-12T01:00:00+00:00",
            "role": "worker-primary", "task_class": "feature-multi-file",
            "from_model": "sonnet", "to_model": "opus",
            "rule": "promote-2x-gate-fail", "evidence": ["t1", "t2"],
        }]
        assert _ledger.evaluate_rebalance(ledger, LADDER) == []
