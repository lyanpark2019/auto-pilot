from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ORCH = str(Path(__file__).resolve().parent.parent / "scripts" / "orchestrator.py")


def _run(cwd: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os
    # _state.STATE_DIR is the RELATIVE path ".planning/auto-pilot" — it resolves
    # against the subprocess CWD, so running with cwd=tmp_path isolates state.
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, ORCH, *args], cwd=cwd,
                          capture_output=True, text=True, env=env)


def _init_running_state(cwd: Path) -> None:
    sd = cwd / ".planning" / "auto-pilot"
    sd.mkdir(parents=True)
    (sd / "state.json").write_text(json.dumps({
        "started_at": "2026-06-10T00:00:00+00:00",
        "spec_path": "x.md", "current_phase": 1, "total_phases": 1,
        "status": "running", "max_workers": 1, "time_box_until": None,
        "phases": [{"phase": 1, "status": "running"}],
        "pivot_detector": {}, "cost_usd": 0.0, "tokens": 0,
    }))


def test_phase_end_success_denied_without_evidence(tmp_path):
    _init_running_state(tmp_path)
    # contracts tree exists but the round has NO evidence
    (tmp_path / ".planning/auto-pilot/contracts/iter-1/phase-1/contract-1/round-1").mkdir(parents=True)
    proc = _run(tmp_path, "phase-end", "--phase", "1", "--status", "success")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "BLOCKED" in proc.stderr
    # state untouched — still running
    state = json.loads((tmp_path / ".planning/auto-pilot/state.json").read_text())
    assert state["status"] == "running"


def test_phase_end_failed_is_exempt(tmp_path):
    _init_running_state(tmp_path)
    proc = _run(tmp_path, "phase-end", "--phase", "1", "--status", "failed")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_phase_end_success_skip_env_allows(tmp_path):
    _init_running_state(tmp_path)
    proc = _run(tmp_path, "phase-end", "--phase", "1", "--status", "success",
                env_extra={"AUTO_PILOT_SKIP_EVIDENCE": "1"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
