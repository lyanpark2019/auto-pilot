from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _round_budget  # noqa: E402


def test_load_findings_missing_file_returns_empty(tmp_path):
    assert _round_budget.load_findings(tmp_path, 1) == {}


def test_load_findings_invalid_json_returns_empty(tmp_path):
    """Malformed JSON must not raise — returns {} so the gate routes to exit 2,
    never an unhandled exit 1 that would skip the round-3 hard stop."""
    (tmp_path / "findings-round-1.json").write_text("{ not json")
    assert _round_budget.load_findings(tmp_path, 1) == {}


def test_load_findings_non_object_returns_empty(tmp_path):
    (tmp_path / "findings-round-2.json").write_text("[1, 2, 3]")
    assert _round_budget.load_findings(tmp_path, 2) == {}


def test_count_findings_skips_non_dict_reviewer_value():
    """A non-dict reviewer entry (e.g. a stray string) must be skipped, not crash."""
    data = {"reviewers": {"codex": {"count": 2}, "claude": "oops"}}
    assert _round_budget.count_findings(data) == 2


def test_count_findings_non_dict_reviewers_map_is_zero():
    assert _round_budget.count_findings({"reviewers": "oops"}) == 0


def test_count_findings_empty_payload_is_zero():
    assert _round_budget.count_findings({}) == 0


def test_count_findings_sums_valid_reviewers():
    data = {"reviewers": {"codex": {"count": 3}, "claude": {"count": 4}}}
    assert _round_budget.count_findings(data) == 7


def test_load_then_count_invalid_json_round_trips_to_zero(tmp_path):
    """End-to-end of the gate's load->count path on malformed input: no crash."""
    (tmp_path / "findings-round-3.json").write_text("{ broken")
    data = _round_budget.load_findings(tmp_path, 3)
    assert data == {}
    assert _round_budget.count_findings(data) == 0


def test_load_findings_valid_round_trips(tmp_path):
    payload = {"reviewers": {"codex": {"count": 1}}}
    (tmp_path / "findings-round-1.json").write_text(json.dumps(payload))
    data = _round_budget.load_findings(tmp_path, 1)
    assert data == payload
    assert _round_budget.count_findings(data) == 1
