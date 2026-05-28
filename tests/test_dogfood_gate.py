"""Tests for scripts/_dogfood_gate.py — Tier 1 + Tier 2 acceptance assertions."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import _contract
import _dogfood_gate as gate


REPO = Path(__file__).resolve().parent.parent
SAMPLE_CONTRACT = REPO / "tests" / "fixtures" / "contracts" / "sample_contract.json"


def _git_init(repo: Path) -> str:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "init"],
        cwd=repo, check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
    ).stdout.strip()


def _phase_commit(repo: Path, phase: int, iter_n: int = 1) -> None:
    (repo / f"phase{phase}.txt").write_text(f"phase {phase}\n")
    subprocess.run(["git", "add", f"phase{phase}.txt"], cwd=repo, check=True)
    msg = (
        f"phase {phase}\n\n"
        f"auto-pilot-iter: {iter_n}\n"
        f"auto-pilot-phase: {phase}\n"
        f"auto-pilot-contract: 1\n"
        f"auto-pilot-idempotency: deadbeef{phase:02d}\n"
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-m", msg],
        cwd=repo, check=True,
    )


def _build_contract_dir(repo: Path, phase: int, base_sha: str) -> Path:
    """Build a valid contract dir with PM-SIGNATURE under repo/.planning/."""
    round_dir = repo / ".planning" / "auto-pilot" / "contracts" / "iter-1" / f"phase-{phase}" / "contract-1" / "round-1"
    round_dir.mkdir(parents=True)

    # Build context bundle so PM-SIGNATURE has real shas
    bundle = round_dir / "context-bundle"
    bundle.mkdir()
    spec_dest = bundle / "spec.md"
    spec_dest.write_text(f"# phase {phase}\n## Phase {phase}\n")
    claude_dest = bundle / "CLAUDE.md"
    claude_dest.write_text("project rules\n")
    spec_sha = hashlib.sha256(spec_dest.read_bytes()).hexdigest()
    claude_sha = hashlib.sha256(claude_dest.read_bytes()).hexdigest()
    (bundle / "MANIFEST.txt").write_text(
        f"{spec_sha}  spec.md\n{claude_sha}  CLAUDE.md\n"
    )

    sample = json.loads(SAMPLE_CONTRACT.read_text())
    contract = dict(sample)
    contract["id"] = f"iter-1/phase-{phase}/contract-1/round-1"
    contract["phase"] = phase
    contract["context_bundle_path"] = str(bundle)
    contract["snapshot_shas"] = {
        "spec": spec_sha,
        "claude_md_chain": [claude_sha],
        "base_sha": base_sha,
    }
    contract["kill_switch_path"] = str(round_dir / "CANCELED")
    contract["review_outputs"] = {
        "codex": str(round_dir / "outputs/codex-reviewer/review.json"),
        "claude": str(round_dir / "outputs/claude-reviewer/review.json"),
        "specialists": {},
    }
    _contract.write_contract(contract, round_dir / "contract.json")
    _contract.write_pm_signature(round_dir, run_id="test-run")
    return round_dir


def _populate_outputs(round_dir: Path, roles: list[str], specialists: list[str] | None = None) -> None:
    """Drop done.marker + exit-code.txt + review.json under outputs/<role>/
    and outputs/specialists/<name>/ for each specialist passed."""
    for role in roles:
        d = round_dir / "outputs" / role
        d.mkdir(parents=True, exist_ok=True)
        (d / "review.json").write_text(json.dumps({"verdict": "APPROVE"}))
        (d / "exit-code.txt").write_text("0\n")
        (d / "done.marker").touch()
    for spec in (specialists or []):
        d = round_dir / "outputs" / "specialists" / spec
        d.mkdir(parents=True, exist_ok=True)
        (d / "review.json").write_text(json.dumps({"verdict": "APPROVE"}))
        (d / "exit-code.txt").write_text("0\n")
        (d / "done.marker").touch()


def _write_state(repo: Path, status: str, phases: int, current: int) -> None:
    sd = repo / ".planning" / "auto-pilot"
    sd.mkdir(parents=True, exist_ok=True)
    (sd / "state.json").write_text(json.dumps({
        "status": status,
        "current_phase": current,
        "total_phases": phases,
        "phases": [
            {"phase": p, "status": "success", "round": 1, "contracts": 1,
             "approved": 1, "started": "2026-05-28T00:00:00+00:00",
             "ended": "2026-05-28T00:01:00+00:00", "commits": ["abc"]}
            for p in range(1, current + 1)
        ],
    }) + "\n")


@pytest.fixture()
def good_repo(tmp_path):
    """Repo with 2 phases successfully completed, contracts signed, no worktrees."""
    base = _git_init(tmp_path)
    _phase_commit(tmp_path, phase=1)
    _phase_commit(tmp_path, phase=2)
    _write_state(tmp_path, status="success", phases=2, current=2)
    _build_contract_dir(tmp_path, phase=1, base_sha=base)
    _build_contract_dir(tmp_path, phase=2, base_sha=base)
    return tmp_path


class TestTier1:
    def test_passes_on_clean_run(self, good_repo):
        report = gate.run_tier1(good_repo, expected_phases=2)
        assert report.passed, report.failures

    def test_fails_when_phase_count_short(self, good_repo):
        # Only 1 phase commit / state
        sd = good_repo / ".planning" / "auto-pilot" / "state.json"
        st = json.loads(sd.read_text())
        st["current_phase"] = 1
        st["phases"] = st["phases"][:1]
        sd.write_text(json.dumps(st))
        report = gate.run_tier1(good_repo, expected_phases=2)
        assert not report.passed
        assert any("current_phase" in f or "1/2" in f or "expected 2" in f for f in report.failures)

    def test_fails_on_missing_signature(self, good_repo):
        sig = good_repo / ".planning" / "auto-pilot" / "contracts" / "iter-1" / "phase-2" / "contract-1" / "round-1" / "PM-SIGNATURE"
        sig.unlink()
        report = gate.run_tier1(good_repo, expected_phases=2)
        assert not report.passed
        assert any("PM-SIGNATURE" in f for f in report.failures)

    def test_fails_on_active_worktree(self, good_repo):
        wt = good_repo / ".planning" / "auto-pilot" / "worktrees" / "iter-1-phase-1-contract-1-round-1"
        wt.mkdir(parents=True)
        report = gate.run_tier1(good_repo, expected_phases=2)
        assert not report.passed
        assert any("worktree" in f for f in report.failures)

    def test_fails_on_missing_trailer(self, tmp_path):
        # Repo with successful state + signed contracts but commits have no trailer
        base = _git_init(tmp_path)
        # Plain commits, no trailers
        (tmp_path / "x.txt").write_text("x\n")
        subprocess.run(["git", "add", "x.txt"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t",
             "commit", "-m", "plain"], cwd=tmp_path, check=True,
        )
        _write_state(tmp_path, status="success", phases=2, current=2)
        _build_contract_dir(tmp_path, phase=1, base_sha=base)
        _build_contract_dir(tmp_path, phase=2, base_sha=base)
        report = gate.run_tier1(tmp_path, expected_phases=2)
        assert not report.passed
        assert any("trailer" in f or "auto-pilot-iter" in f for f in report.failures)


class TestTier2:
    def test_passes_when_outputs_present_no_violations(self, good_repo):
        for phase in (1, 2):
            round_dir = good_repo / ".planning" / "auto-pilot" / "contracts" / "iter-1" / f"phase-{phase}" / "contract-1" / "round-1"
            _populate_outputs(round_dir, ["worker", "codex-reviewer", "claude-reviewer"])
        report = gate.run_tier2(good_repo, expected_phases=2)
        assert report.passed, report.failures

    def test_fails_on_sandbox_violation(self, good_repo):
        for phase in (1, 2):
            round_dir = good_repo / ".planning" / "auto-pilot" / "contracts" / "iter-1" / f"phase-{phase}" / "contract-1" / "round-1"
            _populate_outputs(round_dir, ["worker", "codex-reviewer", "claude-reviewer"])
        viol = good_repo / ".planning" / "auto-pilot" / "sandbox-violations.jsonl"
        viol.write_text(json.dumps({"role": "codex-reviewer", "path": "/etc/passwd"}) + "\n")
        report = gate.run_tier2(good_repo, expected_phases=2)
        assert not report.passed
        assert any("sandbox" in f.lower() for f in report.failures)

    def test_fails_on_missing_done_marker(self, good_repo):
        # Populate outputs but remove one done.marker
        for phase in (1, 2):
            round_dir = good_repo / ".planning" / "auto-pilot" / "contracts" / "iter-1" / f"phase-{phase}" / "contract-1" / "round-1"
            _populate_outputs(round_dir, ["worker", "codex-reviewer", "claude-reviewer"])
        (good_repo / ".planning" / "auto-pilot" / "contracts" / "iter-1" / "phase-1" / "contract-1" / "round-1"
         / "outputs" / "claude-reviewer" / "done.marker").unlink()
        report = gate.run_tier2(good_repo, expected_phases=2)
        assert not report.passed
        assert any("done.marker" in f for f in report.failures)

    def test_specialist_role_checked(self, good_repo):
        """Regression: outputs/specialists/<name>/ must be traversed and checked."""
        for phase in (1, 2):
            round_dir = good_repo / ".planning" / "auto-pilot" / "contracts" / "iter-1" / f"phase-{phase}" / "contract-1" / "round-1"
            _populate_outputs(
                round_dir,
                ["worker", "codex-reviewer", "claude-reviewer"],
                specialists=["security-reviewer"],
            )
        # Sanity: passes when specialist artifacts are present
        report = gate.run_tier2(good_repo, expected_phases=2)
        assert report.passed, report.failures
        # Now break the specialist: missing exit-code.txt → failure
        bad = good_repo / ".planning" / "auto-pilot" / "contracts" / "iter-1" / "phase-1" / "contract-1" / "round-1" / "outputs" / "specialists" / "security-reviewer" / "exit-code.txt"
        bad.unlink()
        report2 = gate.run_tier2(good_repo, expected_phases=2)
        assert not report2.passed
        assert any("exit-code.txt" in f and "security-reviewer" in f for f in report2.failures)


class TestCli:
    def test_cli_tier1_exit_0_on_pass(self, good_repo):
        res = subprocess.run(
            ["python3", str(REPO / "scripts" / "_dogfood_gate.py"),
             "--tier", "1", "--repo-root", str(good_repo), "--phases", "2"],
            capture_output=True, text=True,
        )
        assert res.returncode == 0, res.stdout + res.stderr
        payload = json.loads(res.stdout)
        assert payload["passed"] is True
        assert payload["tier"] == 1

    def test_cli_tier1_exit_1_on_fail(self, tmp_path):
        # Empty repo — no state.json, no contracts
        res = subprocess.run(
            ["python3", str(REPO / "scripts" / "_dogfood_gate.py"),
             "--tier", "1", "--repo-root", str(tmp_path), "--phases", "2"],
            capture_output=True, text=True,
        )
        assert res.returncode == 1
        payload = json.loads(res.stdout)
        assert payload["passed"] is False
        assert payload["failures"]


def test_tier_scripts_have_executable_bit():
    for name in ("dogfood_tier1.sh", "dogfood_tier2.sh"):
        p = REPO / "scripts" / name
        mode = p.stat().st_mode
        assert mode & 0o111, f"{name} not executable"


def test_tier_scripts_have_strict_mode():
    for name in ("dogfood_tier1.sh", "dogfood_tier2.sh"):
        text = (REPO / "scripts" / name).read_text()
        assert "set -euo pipefail" in text


def test_smoke_spec_parses_to_two_phases(tmp_path, monkeypatch):
    import orchestrator
    monkeypatch.chdir(tmp_path)
    spec = REPO / "docs" / "specs" / "2026-05-28-dogfood-smoke.md"
    rc = orchestrator.main(["init", "--spec", str(spec), "--max-workers", "1"])
    assert rc == 0
    state = json.loads(Path(".planning/auto-pilot/state.json").read_text())
    assert state["total_phases"] == 2
