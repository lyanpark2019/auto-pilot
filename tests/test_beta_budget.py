"""Tests for β round-budget gate (round-2 W2):
  ⓗ    round-budget subcommand
"""
from __future__ import annotations

import json
from pathlib import Path


class TestRoundBudget:
    def _write_findings(self, score_dir: Path, round_n: int,
                        claude_count: int, codex_count: int) -> None:
        data = {
            "round": round_n,
            "reviewers": {
                "claude": {
                    "count": claude_count,
                    "findings": [
                        {"hash": f"h{i}", "severity": "P2",
                         "asset": "test", "issue": "x"}
                        for i in range(claude_count)
                    ],
                },
                "codex": {
                    "count": codex_count,
                    "findings": [
                        {"hash": f"c{i}", "severity": "P2",
                         "asset": "test", "issue": "y"}
                        for i in range(codex_count)
                    ],
                },
            },
        }
        path = score_dir / f"findings-round-{round_n}.json"
        path.write_text(json.dumps(data, indent=2))

    def test_n_less_than_3_informational(self, in_tmp_cwd, tmp_path, capsys):
        import orchestrator
        score_dir = tmp_path / "score"
        score_dir.mkdir()
        self._write_findings(score_dir, 2, claude_count=10, codex_count=5)
        rc = orchestrator.main(["round-budget", "--score-dir", str(score_dir), "--round", "2"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["count"] == 15
        assert out["status"] == "informational"

    def test_n_eq_3_count_increased_hard_stop(self, in_tmp_cwd, tmp_path, capsys):
        import orchestrator
        score_dir = tmp_path / "score"
        score_dir.mkdir()
        self._write_findings(score_dir, 2, claude_count=10, codex_count=5)  # total 15
        self._write_findings(score_dir, 3, claude_count=12, codex_count=8)  # total 20
        rc = orchestrator.main(["round-budget", "--score-dir", str(score_dir), "--round", "3"])
        assert rc == 3
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert "HARD-STOP" in out["verdict"]
        assert "전략 전환 필요" in captured.err

    def test_n_eq_3_count_decreased_round4_cap(self, in_tmp_cwd, tmp_path, capsys):
        import orchestrator
        score_dir = tmp_path / "score"
        score_dir.mkdir()
        self._write_findings(score_dir, 2, claude_count=20, codex_count=10)  # total 30
        self._write_findings(score_dir, 3, claude_count=8, codex_count=4)   # total 12
        rc = orchestrator.main(["round-budget", "--score-dir", str(score_dir), "--round", "3"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert "final cap" in out["verdict"]

    def test_missing_file_returns_2(self, in_tmp_cwd, tmp_path, capsys):
        import orchestrator
        score_dir = tmp_path / "score"
        score_dir.mkdir()
        # round 3 requires both round-2 and round-3 files
        self._write_findings(score_dir, 2, claude_count=5, codex_count=5)
        # round-3 missing
        rc = orchestrator.main(["round-budget", "--score-dir", str(score_dir), "--round", "3"])
        assert rc == 2

    def test_n_eq_3_equal_count_is_hard_stop(self, in_tmp_cwd, tmp_path, capsys):
        """Equal count (not strictly decreasing) → HARD-STOP."""
        import orchestrator
        score_dir = tmp_path / "score"
        score_dir.mkdir()
        self._write_findings(score_dir, 2, claude_count=10, codex_count=5)  # 15
        self._write_findings(score_dir, 3, claude_count=10, codex_count=5)  # 15 same
        rc = orchestrator.main(["round-budget", "--score-dir", str(score_dir), "--round", "3"])
        assert rc == 3
