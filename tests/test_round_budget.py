from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _round_budget  # noqa: E402
import orchestrator  # noqa: E402


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


# ---------------------------------------------------------------------------
# CLI handler tests (cmd_round_budget via orchestrator.main)
# ---------------------------------------------------------------------------

def _write_findings(d: Path, r: int, count: int) -> None:
    payload = {"reviewers": {"codex": {"count": count}}}
    (d / f"findings-round-{r}.json").write_text(json.dumps(payload))


class TestCmdRoundBudgetCli:
    """Drive cmd_round_budget through orchestrator.main to verify CLI wiring."""

    def test_n_lt_3_present_file_returns_0(self, tmp_path, capsys):
        _write_findings(tmp_path, 2, 5)
        rc = orchestrator.main(["round-budget", "--score-dir", str(tmp_path), "--round", "2"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["round"] == 2
        assert out["count"] == 5
        assert out["status"] == "informational"

    def test_n_lt_3_missing_file_returns_2(self, tmp_path):
        rc = orchestrator.main(["round-budget", "--score-dir", str(tmp_path), "--round", "2"])
        assert rc == 2

    def test_n_eq_3_count_curr_ge_prev_returns_3_hard_stop(self, tmp_path, capsys):
        _write_findings(tmp_path, 2, 3)
        _write_findings(tmp_path, 3, 3)  # curr == prev → HARD-STOP
        rc = orchestrator.main(["round-budget", "--score-dir", str(tmp_path), "--round", "3"])
        assert rc == 3
        out = json.loads(capsys.readouterr().out)
        assert out["verdict"] == "HARD-STOP: 전략 전환 필요"
        assert out["count_curr"] == 3
        assert out["count_prev"] == 3

    def test_n_eq_3_count_curr_lt_prev_returns_0(self, tmp_path, capsys):
        _write_findings(tmp_path, 2, 5)
        _write_findings(tmp_path, 3, 3)  # curr < prev → round 4 = final cap
        rc = orchestrator.main(["round-budget", "--score-dir", str(tmp_path), "--round", "3"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["verdict"] == "round 4 = final cap"

    def test_n_gt_3_missing_file_returns_2(self, tmp_path):
        # Only round-4 file present but round-3 missing → rc 2
        _write_findings(tmp_path, 4, 1)
        rc = orchestrator.main(["round-budget", "--score-dir", str(tmp_path), "--round", "5"])
        assert rc == 2

    def test_n_gt_3_count_curr_ge_prev_returns_3_hard_stop(self, tmp_path, capsys):
        _write_findings(tmp_path, 4, 2)
        _write_findings(tmp_path, 5, 2)  # curr == prev → HARD-STOP
        rc = orchestrator.main(["round-budget", "--score-dir", str(tmp_path), "--round", "5"])
        assert rc == 3
        out = json.loads(capsys.readouterr().out)
        assert out["verdict"] == "HARD-STOP: 전략 전환 필요"

    def test_n_gt_3_count_curr_lt_prev_returns_0(self, tmp_path, capsys):
        _write_findings(tmp_path, 4, 5)
        _write_findings(tmp_path, 5, 3)  # curr < prev → progress, rc 0
        rc = orchestrator.main(["round-budget", "--score-dir", str(tmp_path), "--round", "5"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["verdict"] == "round 4 = final cap"
