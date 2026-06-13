"""Tests for structured-result parsing, JSONL ledger, and wall-clock watchdog."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import _budget  # noqa: E402


class TestParseResultJson:
    def test_extracts_cost_and_tokens(self) -> None:
        line = json.dumps({
            "type": "result",
            "total_cost_usd": 1.23,
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 20,
            },
        })
        result = _budget.parse_result_json(line)
        assert result == (1.23, 170)

    def test_returns_none_without_result_line(self) -> None:
        text = "some random output\nno structured lines here\n"
        assert _budget.parse_result_json(text) is None

    def test_ignores_malformed_lines(self) -> None:
        text = "{not json\n" + json.dumps({"type": "result", "total_cost_usd": 0.5, "usage": {}})
        result = _budget.parse_result_json(text)
        assert result is not None
        assert result[0] == 0.5

    def test_last_result_wins(self) -> None:
        line1 = json.dumps({"type": "result", "total_cost_usd": 1.0, "usage": {"input_tokens": 10}})
        line2 = json.dumps({"type": "result", "total_cost_usd": 2.5, "usage": {"input_tokens": 20}})
        result = _budget.parse_result_json(line1 + "\n" + line2)
        assert result is not None
        assert result[0] == 2.5
        assert result[1] == 20

    def test_ignores_bool_token_values(self) -> None:
        line = json.dumps({
            "type": "result",
            "total_cost_usd": 0.1,
            "usage": {
                "input_tokens": 50,
                "cache_tokens": True,  # bool should be excluded
            },
        })
        result = _budget.parse_result_json(line)
        assert result is not None
        assert result[1] == 50  # only the non-bool int is counted

    def test_non_result_type_skipped(self) -> None:
        line = json.dumps({"type": "assistant", "total_cost_usd": 9.99})
        assert _budget.parse_result_json(line) is None

    def test_missing_total_cost_yields_zero(self) -> None:
        line = json.dumps({"type": "result", "usage": {"input_tokens": 10}})
        result = _budget.parse_result_json(line)
        assert result == (0.0, 10)


class TestParseSessionUsage:
    def test_prefers_structured_over_regex(self, tmp_path: Path) -> None:
        log = tmp_path / "iter.log"
        structured_line = json.dumps({
            "type": "result",
            "total_cost_usd": 9.99,
            "usage": {"input_tokens": 500},
        })
        log.write_text(f"Total cost: $0.42 USD\nTokens used: 1234\n{structured_line}\n")
        cost, tokens = _budget.parse_session_usage(log)
        assert cost == 9.99
        assert tokens == 500

    def test_falls_back_to_regex(self, tmp_path: Path) -> None:
        log = tmp_path / "iter.log"
        log.write_text("Total cost: $0.42 USD\nTokens used: 1234\n")
        cost, tokens = _budget.parse_session_usage(log)
        assert cost == 0.42
        assert tokens == 1234


class TestAppendUsageLedger:
    def test_writes_one_jsonl_line(self, tmp_path: Path) -> None:
        ledger = tmp_path / "logs" / "usage.jsonl"
        _budget.append_usage_ledger(ledger, {"iter": 1, "cost_usd": 0.5})
        _budget.append_usage_ledger(ledger, {"iter": 2, "cost_usd": 0.7})
        lines = ledger.read_text().splitlines()
        assert len(lines) == 2
        r1 = json.loads(lines[0])
        r2 = json.loads(lines[1])
        assert r1["iter"] == 1
        assert r2["iter"] == 2
        assert r1["cost_usd"] == 0.5

    def test_oserror_is_swallowed(self, tmp_path: Path) -> None:
        # Make parent path an existing file so mkdir fails when trying to create it as dir
        blocker = tmp_path / "logs"
        blocker.write_text("I am a file, not a dir")
        ledger = blocker / "usage.jsonl"
        # Should not raise
        _budget.append_usage_ledger(ledger, {"iter": 1})

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        ledger = tmp_path / "a" / "b" / "c" / "usage.jsonl"
        _budget.append_usage_ledger(ledger, {"x": 1})
        assert ledger.exists()


class TestCheckWallClock:
    def test_fires_at_deadline(self) -> None:
        assert _budget.check_wall_clock(100.0, 100.0) == "time-cap"

    def test_fires_past_deadline(self) -> None:
        assert _budget.check_wall_clock(100.0, 101.0) == "time-cap"

    def test_no_fire_before_deadline(self) -> None:
        assert _budget.check_wall_clock(100.0, 99.9) is None

    def test_none_deadline_never_fires(self) -> None:
        assert _budget.check_wall_clock(None, 123_456_789.0) is None
