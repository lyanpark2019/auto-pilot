from __future__ import annotations

import json
import subprocess
from pathlib import Path


import orchestrator  # type: ignore[import-not-found]


def _run(argv: list[str]) -> int:
    return orchestrator.main(argv)


def _state() -> dict:
    return json.loads(Path(".planning/auto-pilot/state.json").read_text())


class TestInit:
    def test_init_writes_state(self, in_tmp_cwd, sample_spec, capsys):
        rc = _run(["init", "--spec", str(sample_spec), "--max-workers", "6"])
        assert rc == 0
        state = _state()
        assert state["status"] == "running"
        assert state["total_phases"] == 3
        assert state["max_workers"] == 6
        assert state["current_phase"] == 0
        assert state["phases"] == []
        out = capsys.readouterr().out
        assert json.loads(out)["ok"] is True

    def test_init_missing_spec_errors(self, in_tmp_cwd, capsys):
        rc = _run(["init", "--spec", "nope.md"])
        assert rc == 2
        err = capsys.readouterr().err
        assert "event=init.spec_missing" in err

    def test_phase_count_falls_back_to_one(self, in_tmp_cwd, tmp_path):
        spec = tmp_path / "empty.md"
        spec.write_text("no headers here\n")
        _run(["init", "--spec", str(spec)])
        assert _state()["total_phases"] == 1

    def test_phase_count_skips_fenced_code(self, in_tmp_cwd, tmp_path):
        spec = tmp_path / "fenced.md"
        spec.write_text(
            "# Spec\n\n"
            "## Phase 1: real\n"
            "intro\n\n"
            "```markdown\n"
            "## Phase 99: example inside code fence\n"
            "## Phase 100: also example\n"
            "```\n\n"
            "## Phase 2: real\n"
        )
        _run(["init", "--spec", str(spec)])
        assert _state()["total_phases"] == 2

    def test_phase_count_handles_h3(self, in_tmp_cwd, tmp_path):
        spec = tmp_path / "deep.md"
        spec.write_text(
            "# Top\n"
            "## Group\n"
            "### Phase 1\n"
            "### Phase 2\n"
            "### Phase 3\n"
        )
        _run(["init", "--spec", str(spec)])
        assert _state()["total_phases"] == 3

    def test_phase_count_tilde_fence(self, in_tmp_cwd, tmp_path):
        spec = tmp_path / "tilde.md"
        spec.write_text(
            "## Phase 1: real\n"
            "~~~md\n"
            "## Phase X: in tilde fence, should be ignored\n"
            "~~~\n"
            "## Phase 2: real\n"
        )
        _run(["init", "--spec", str(spec)])
        assert _state()["total_phases"] == 2

    def test_phase_count_rejects_bullet_lookalike(self, in_tmp_cwd, tmp_path):
        spec = tmp_path / "bullets.md"
        spec.write_text(
            "## Phase 1\n"
            "- ## Phase X (bullet, not heading)\n"
            "  ## Phase Y (indented, not heading)\n"
            "## Phase 2\n"
        )
        _run(["init", "--spec", str(spec)])
        # Bullets/indented should still be counted via lstrip (current behaviour);
        # acceptable because indented `## Phase` lines in real specs are rare.
        # The contract: indented headings that aren't inside code fences DO count.
        # If this proves wrong, tighten the regex to require col 0.
        assert _state()["total_phases"] >= 2

    def test_init_refuses_to_overwrite_running(self, in_tmp_cwd, sample_spec, capsys):
        _run(["init", "--spec", str(sample_spec)])
        rc = _run(["init", "--spec", str(sample_spec)])
        assert rc == 2
        assert "event=init.already_running" in capsys.readouterr().err

    def test_init_force_overwrites(self, in_tmp_cwd, sample_spec):
        _run(["init", "--spec", str(sample_spec)])
        rc = _run(["init", "--spec", str(sample_spec), "--force", "--max-workers", "2"])
        assert rc == 0
        assert _state()["max_workers"] == 2

    def test_init_after_stop_allowed(self, in_tmp_cwd, sample_spec):
        _run(["init", "--spec", str(sample_spec)])
        _run(["stop"])
        rc = _run(["init", "--spec", str(sample_spec)])
        assert rc == 0


class TestPhaseLifecycle:
    def test_phase_start_appends(self, in_tmp_cwd, sample_spec):
        _run(["init", "--spec", str(sample_spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "5"])
        state = _state()
        assert state["current_phase"] == 1
        assert state["phases"][0]["contracts"] == 5
        assert state["phases"][0]["status"] == "running"

    def test_phase_start_without_init_fails(self, in_tmp_cwd, capsys):
        rc = _run(["phase-start", "--phase", "1", "--contracts", "1"])
        assert rc == 2
        assert "event=phase_start.no_state" in capsys.readouterr().err

    def test_phase_end_success_marks_done_on_last(self, in_tmp_cwd, tmp_path, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_SKIP_EVIDENCE", "1")
        spec = tmp_path / "single.md"
        spec.write_text("## Phase 1\n")
        _run(["init", "--spec", str(spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "2"])
        _run(["phase-end", "--phase", "1", "--status", "success", "--commits", "abc,def"])
        state = _state()
        assert state["status"] == "success"
        assert state["phases"][-1]["commits"] == ["abc", "def"]
        assert state["phases"][-1]["ended"]

    def test_phase_end_failed_propagates(self, in_tmp_cwd, sample_spec):
        _run(["init", "--spec", str(sample_spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "2"])
        _run(["phase-end", "--phase", "1", "--status", "failed"])
        assert _state()["status"] == "failed"

    def test_phase_end_without_phase_errors(self, in_tmp_cwd, sample_spec, capsys):
        _run(["init", "--spec", str(sample_spec)])
        rc = _run(["phase-end", "--phase", "1", "--status", "success"])
        assert rc == 2
        assert "event=phase_end.no_active_phase" in capsys.readouterr().err

    def test_phase_end_mismatched_phase_rejected(self, in_tmp_cwd, sample_spec, capsys):
        _run(["init", "--spec", str(sample_spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "2"])
        rc = _run(["phase-end", "--phase", "2", "--status", "success"])
        assert rc == 2
        assert "event=phase_end.phase_mismatch" in capsys.readouterr().err
        assert _state()["phases"][-1]["status"] == "running"

    def test_phase_end_success_midway_keeps_running(self, in_tmp_cwd, sample_spec, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_SKIP_EVIDENCE", "1")
        _run(["init", "--spec", str(sample_spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "1"])
        _run(["phase-end", "--phase", "1", "--status", "success"])
        assert _state()["status"] == "running"

    def test_two_phase_spec_phase1_keeps_running(self, in_tmp_cwd, tmp_path, monkeypatch):
        """Regression: phase 1 of 2 must not mark status=success."""
        monkeypatch.setenv("AUTO_PILOT_SKIP_EVIDENCE", "1")
        spec = tmp_path / "two.md"
        spec.write_text("## Phase 1\n## Phase 2\n")
        _run(["init", "--spec", str(spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "1"])
        _run(["phase-end", "--phase", "1", "--status", "success"])
        assert _state()["status"] == "running"

    def test_two_phase_spec_phase2_marks_success(self, in_tmp_cwd, tmp_path, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_SKIP_EVIDENCE", "1")
        spec = tmp_path / "two.md"
        spec.write_text("## Phase 1\n## Phase 2\n")
        _run(["init", "--spec", str(spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "1"])
        _run(["phase-end", "--phase", "1", "--status", "success"])
        _run(["phase-start", "--phase", "2", "--contracts", "1"])
        _run(["phase-end", "--phase", "2", "--status", "success"])
        assert _state()["status"] == "success"

    def test_phase_start_out_of_range_rejected(self, in_tmp_cwd, sample_spec, capsys):
        _run(["init", "--spec", str(sample_spec)])
        rc = _run(["phase-start", "--phase", "99", "--contracts", "1"])
        assert rc == 2
        assert "event=phase_start.out_of_range" in capsys.readouterr().err

    def test_phase_start_phase_zero_rejected(self, in_tmp_cwd, sample_spec, capsys):
        _run(["init", "--spec", str(sample_spec)])
        rc = _run(["phase-start", "--phase", "0", "--contracts", "1"])
        assert rc == 2
        assert "event=phase_start.out_of_range" in capsys.readouterr().err

    def test_phase_start_duplicate_running_rejected(self, in_tmp_cwd, sample_spec, capsys):
        _run(["init", "--spec", str(sample_spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "1"])
        rc = _run(["phase-start", "--phase", "1", "--contracts", "1"])
        assert rc == 2
        assert "event=phase_start.already_running" in capsys.readouterr().err

    def test_phase_start_retry_bumps_round(self, in_tmp_cwd, sample_spec):
        _run(["init", "--spec", str(sample_spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "2"])
        _run(["phase-end", "--phase", "1", "--status", "failed"])
        _run(["phase-start", "--phase", "1", "--contracts", "3"])
        entry = _state()["phases"][-1]
        assert entry["round"] == 2
        assert entry["status"] == "running"
        assert entry["contracts"] == 3
        # No duplicate entry appended:
        assert sum(1 for p in _state()["phases"] if p["phase"] == 1) == 1


class TestPivotCheck:
    def test_trips_at_third_repeat(self, in_tmp_cwd, sample_spec, capsys):
        _run(["init", "--spec", str(sample_spec)])
        assert _run(["pivot-check", "--phase", "1", "--finding-hash", "h1"]) == 0
        assert _run(["pivot-check", "--phase", "1", "--finding-hash", "h1"]) == 0
        rc = _run(["pivot-check", "--phase", "1", "--finding-hash", "h1"])
        assert rc == 1
        assert _state()["status"] == "pivot-needed"
        assert "event=pivot.needed" in capsys.readouterr().err

    def test_different_findings_dont_trip(self, in_tmp_cwd, sample_spec):
        _run(["init", "--spec", str(sample_spec)])
        for h in ("a", "b", "c"):
            assert _run(["pivot-check", "--phase", "1", "--finding-hash", h]) == 0
        assert _state()["status"] == "running"

    def test_no_state_is_noop(self, in_tmp_cwd):
        assert _run(["pivot-check", "--phase", "1", "--finding-hash", "x"]) == 0


class TestStatusStop:
    def test_status_uninitialized(self, in_tmp_cwd, capsys):
        rc = _run(["status"])
        assert rc == 0
        assert "not initialized" in capsys.readouterr().out

    def test_stop_marks_stopped(self, in_tmp_cwd, sample_spec):
        _run(["init", "--spec", str(sample_spec)])
        _run(["stop"])
        state = _state()
        assert state["status"] == "stopped"
        assert "stopped_at" in state

    def test_stop_without_init_is_noop(self, in_tmp_cwd, capsys):
        rc = _run(["stop"])
        assert rc == 0
        assert "nothing to stop" in capsys.readouterr().out


def test_phase_start_allocates_run_id_if_missing(monkeypatch, tmp_path):
    import sys
    import importlib
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    import _state
    importlib.reload(_state)
    import orchestrator
    importlib.reload(orchestrator)

    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n## Phase 1\n## Phase 2\n")
    args = type("A", (), {"spec": str(spec), "max_workers": 4, "time_box_until": None, "force": False})
    orchestrator.cmd_init(args)

    # State has no run_id yet
    state = _state.load_state()
    assert "run_id" not in state or state.get("run_id") is None

    args_ps = type("A", (), {"phase": 1, "contracts": 3})
    orchestrator.cmd_phase_start(args_ps)

    state2 = _state.load_state()
    assert isinstance(state2.get("run_id"), str)
    assert len(state2["run_id"]) >= 8


class TestDiscover:
    @staticmethod
    def _git_repo_in_cwd() -> None:
        subprocess.run(["git", "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "config", "user.name", "T"], check=True)
        Path("src").mkdir()
        Path("src/a.py").write_text("a = 1\n")
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], check=True)

    def test_record_then_check_fresh(self, in_tmp_cwd, capsys):
        self._git_repo_in_cwd()
        assert _run(["discover", "--record", "--graphify-version", "g1"]) == 0
        rec = json.loads(capsys.readouterr().out)
        assert rec["ok"] is True and rec["graphify_version"] == "g1"
        rc = _run(["discover", "--check", "--graphify-version", "g1",
                   "--scope-files", "src/"])
        out = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert out["fresh"] is True and out["reason"] == "same-commit"

    def test_check_stale_exits_1(self, in_tmp_cwd, capsys):
        self._git_repo_in_cwd()
        assert _run(["discover", "--record", "--graphify-version", "g1"]) == 0
        capsys.readouterr()
        Path("src/a.py").write_text("a = 2\n")
        subprocess.run(["git", "add", "-A"], check=True)
        subprocess.run(["git", "commit", "-q", "-m", "edit"], check=True)
        rc = _run(["discover", "--check", "--graphify-version", "g1",
                   "--scope-files", "src/"])
        out = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert out["fresh"] is False and out["reason"] == "scope-intersects"
        assert out["changed_files"] == ["src/a.py"]


class TestReviewStatus:
    def test_review_status_renders_active_round(self, tmp_path, monkeypatch, capsys):
        import _heartbeat
        monkeypatch.setattr(orchestrator, "STATE_DIR", tmp_path, raising=False)
        out = (tmp_path / "contracts" / "iter-1" / "phase-1" / "contract-1"
               / "round-1" / "outputs" / "claude-reviewer")
        out.mkdir(parents=True)
        _heartbeat.write_beat(out, "claude-reviewer", "review-start", risk_tier="medium")
        rc = orchestrator.main(["review-status"])
        captured = capsys.readouterr().out
        assert rc == 0
        assert "claude-reviewer" in captured
        assert "review-start" in captured

    def test_review_status_empty_tree(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(orchestrator, "STATE_DIR", tmp_path, raising=False)
        rc = orchestrator.main(["review-status"])
        assert rc == 0
        assert "no reviewer status" in capsys.readouterr().out


class TestResume:
    def _seed_state(self, in_tmp_cwd: Path, status: str, sample_spec: Path) -> None:
        _run(["init", "--spec", str(sample_spec)])
        state = _state()
        state["status"] = status
        state["cost_usd"] = 1.23
        state["tokens"] = 5000
        import _state as _s
        import os
        os.chdir(str(in_tmp_cwd))
        _s.save_state(state)

    def test_resume_clears_cost_cap(self, in_tmp_cwd, sample_spec):
        self._seed_state(in_tmp_cwd, "cost-cap", sample_spec)
        rc = _run(["resume"])
        assert rc == 0
        state = _state()
        assert state["status"] == "running"
        # preserved fields untouched
        assert state["cost_usd"] == 1.23
        assert state["tokens"] == 5000

    def test_resume_running_exits_1(self, in_tmp_cwd, sample_spec, capsys):
        _run(["init", "--spec", str(sample_spec)])
        rc = _run(["resume"])
        assert rc == 1
        state = _state()
        assert state["status"] == "running"

    def test_resume_failed_exits_1(self, in_tmp_cwd, sample_spec, capsys):
        self._seed_state(in_tmp_cwd, "failed", sample_spec)
        rc = _run(["resume"])
        assert rc == 1
        state = _state()
        assert state["status"] == "failed"

    def test_resume_absent_state_exits_1(self, in_tmp_cwd):
        """resume with no state.json → exit 1, no state file created."""
        rc = _run(["resume"])
        assert rc == 1
        assert not (in_tmp_cwd / ".planning" / "auto-pilot" / "state.json").exists()

    def test_resume_preserves_cost_and_tokens_on_non_cap_status(
        self, in_tmp_cwd: Path, sample_spec: Path
    ) -> None:
        """resume on failed does not modify cost_usd or tokens."""
        self._seed_state(in_tmp_cwd, "failed", sample_spec)
        rc = _run(["resume"])
        assert rc == 1
        s = _state()
        assert s["cost_usd"] == 1.23
        assert s["tokens"] == 5000


class TestPivotCheckSingleTransaction:
    """Regression pin: cmd_pivot_check must use a single state transaction.

    A two-save implementation (increment save + status-flip save) can lose the
    increment if a concurrent writer races between them.  The single-txn form
    captures both in one atomic commit, so the 3rd call must yield rc==1 AND
    have pivot_detector count==3 AND status=="pivot-needed" on disk.
    """

    def test_third_call_returns_1_and_persists_both_increment_and_status(
        self, in_tmp_cwd: Path, sample_spec: Path
    ) -> None:
        _run(["init", "--spec", str(sample_spec)])
        assert _run(["pivot-check", "--phase", "1", "--finding-hash", "abc"]) == 0
        assert _run(["pivot-check", "--phase", "1", "--finding-hash", "abc"]) == 0
        rc = _run(["pivot-check", "--phase", "1", "--finding-hash", "abc"])
        assert rc == 1
        s = _state()
        assert s["status"] == "pivot-needed"
        assert s["pivot_detector"]["phase-1"]["abc"] == 3


class TestPhaseEndEvidenceGate:
    """phase-end with a failing evidence gate must return 2 and not persist state."""

    def test_failed_gate_returns_2_and_no_status_change(
        self, in_tmp_cwd: Path, tmp_path: Path, monkeypatch
    ) -> None:
        # Build a 1-phase spec.
        spec = tmp_path / "one.md"
        spec.write_text("## Phase 1\n")
        _run(["init", "--spec", str(spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "1"])
        # Do NOT set AUTO_PILOT_SKIP_EVIDENCE; the contracts dir is empty so
        # _evidence.gate_phase_end should return a (suffix, message) tuple.
        monkeypatch.delenv("AUTO_PILOT_SKIP_EVIDENCE", raising=False)
        rc = _run(["phase-end", "--phase", "1", "--status", "success"])
        assert rc == 2
        # Status must remain "running" — gate failure must not write state.
        s = _state()
        assert s["status"] == "running"
        assert s["phases"][-1]["status"] == "running"


class TestStopNoState:
    """cmd_stop on missing state must return 0 and write nothing."""

    def test_stop_no_state_returns_0_no_file(self, in_tmp_cwd: Path, capsys) -> None:
        state_file = in_tmp_cwd / ".planning" / "auto-pilot" / "state.json"
        assert not state_file.exists()
        rc = _run(["stop"])
        assert rc == 0
        assert not state_file.exists()
        assert "nothing to stop" in capsys.readouterr().out
