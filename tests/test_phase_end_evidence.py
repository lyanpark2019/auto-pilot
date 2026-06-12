from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _contract  # noqa: E402

ORCH = str(Path(__file__).resolve().parent.parent / "scripts" / "orchestrator.py")
REVIEWERS = ("codex-reviewer", "claude-reviewer")


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


def _build_passing_round(contract_dir: Path) -> None:
    """Write a complete passing evidence chain for one contract under contract_dir/round-1."""
    round_dir = contract_dir / "round-1"
    diff_text = b"diff --git a b\n"
    sha = _contract._sha256(diff_text)
    (round_dir / "review-input").mkdir(parents=True)
    (round_dir / "tickets").mkdir()
    (round_dir / "review-input" / "frozen.diff").write_bytes(diff_text)
    (round_dir / "review-input" / "frozen.diff.sha256").write_text(sha + "\n")
    (round_dir / "contract.json").write_text(json.dumps({"id": "iter-1/phase-1/contract-1/round-1"}))
    bundle = round_dir / "context-bundle"
    bundle.mkdir()
    (bundle / "MANIFEST.txt").write_text("fixture\n")
    _contract.write_pm_signature(round_dir, run_id="test-run")
    for role in REVIEWERS:
        (round_dir / "tickets" / f"{role}.json").write_text(json.dumps({"diff_sha256": sha}))
        out = round_dir / "outputs" / role
        out.mkdir(parents=True)
        review = {
            "schema_version": 1,
            "reviewer": role,
            "contract_id": "iter-1/phase-1/contract-1/round-1",
            "verdict": "APPROVE",
            "scope_check": "PASS",
            "findings": [],
            "verify_rerun": {"cmd": "pytest", "exit_code": 0},
            "reviewer_meta": {
                "model": "test",
                "started_at": "2026-06-10T00:00:00+00:00",
                "ended_at": "2026-06-10T00:00:01+00:00",
            },
        }
        (out / "review.json").write_text(json.dumps(review))


def test_phase_end_approved_set_from_evidence_count(tmp_path):
    """phase-end --status success sets phases[0]['approved'] to the count of evidence-passing contracts."""
    _init_running_state(tmp_path)
    contracts_root = tmp_path / ".planning" / "auto-pilot" / "contracts"
    contract_dir = contracts_root / "iter-1" / "phase-1" / "contract-1"
    contract_dir.mkdir(parents=True)
    _build_passing_round(contract_dir)

    proc = _run(tmp_path, "phase-end", "--phase", "1", "--status", "success")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    state = json.loads((tmp_path / ".planning/auto-pilot/state.json").read_text())
    assert state["phases"][0]["approved"] == 1, (
        f"expected approved=1, got {state['phases'][0].get('approved')}"
    )


def test_phase_end_approved_stays_zero_on_failed(tmp_path):
    """phase-end --status failed does not set approved (stays 0)."""
    _init_running_state(tmp_path)
    proc = _run(tmp_path, "phase-end", "--phase", "1", "--status", "failed")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    state = json.loads((tmp_path / ".planning/auto-pilot/state.json").read_text())
    assert state["phases"][0].get("approved", 0) == 0
