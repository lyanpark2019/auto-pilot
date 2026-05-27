from __future__ import annotations

import json
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

    def test_phase_end_success_marks_done_on_last(self, in_tmp_cwd, tmp_path):
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

    def test_phase_end_success_midway_keeps_running(self, in_tmp_cwd, sample_spec):
        _run(["init", "--spec", str(sample_spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "1"])
        _run(["phase-end", "--phase", "1", "--status", "success"])
        assert _state()["status"] == "running"

    def test_two_phase_spec_phase1_keeps_running(self, in_tmp_cwd, tmp_path):
        """Regression: phase 1 of 2 must not mark status=success."""
        spec = tmp_path / "two.md"
        spec.write_text("## Phase 1\n## Phase 2\n")
        _run(["init", "--spec", str(spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "1"])
        _run(["phase-end", "--phase", "1", "--status", "success"])
        assert _state()["status"] == "running"

    def test_two_phase_spec_phase2_marks_success(self, in_tmp_cwd, tmp_path):
        spec = tmp_path / "two.md"
        spec.write_text("## Phase 1\n## Phase 2\n")
        _run(["init", "--spec", str(spec)])
        _run(["phase-start", "--phase", "1", "--contracts", "1"])
        _run(["phase-end", "--phase", "1", "--status", "success"])
        _run(["phase-start", "--phase", "2", "--contracts", "1"])
        _run(["phase-end", "--phase", "2", "--status", "success"])
        assert _state()["status"] == "success"


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
