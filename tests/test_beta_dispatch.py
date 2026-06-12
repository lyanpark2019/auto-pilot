"""Tests for β dispatch gate items (round-2 W2):
  ⓓ-7②  dispatch-contract-check subcommand + layer-2 gate
  ⓓ-9   pm_preflight.sh + preflight gate in prepare_subagent_ticket
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest



ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "contracts" / "sample_contract.json"


def _make_contract_dir(tmp_path: Path) -> Path:
    import _contract
    contract = json.loads(FIXTURE.read_text())
    dest = tmp_path / "contracts" / "iter-1/phase-1/contract-1/round-1"
    dest.mkdir(parents=True)
    bundle = dest / "context-bundle"
    bundle.mkdir()
    (bundle / "spec.md").write_text("# spec\n")
    (bundle / "MANIFEST.txt").write_text(_contract._sha256(b"# spec\n") + "  spec.md\n")
    contract["context_bundle_path"] = str(bundle)
    contract["snapshot_shas"]["spec"] = _contract._sha256(b"# spec\n")
    contract["snapshot_shas"]["claude_md_chain"] = []
    _contract.write_contract(contract, dest / "contract.json")
    _contract.write_pm_signature(dest, run_id="run-test")
    return dest


def _signature_status(contract_dir: Path) -> dict[str, object]:
    import _contract
    sig_path = contract_dir / "PM-SIGNATURE"
    sig = json.loads(sig_path.read_text())
    return {
        "verified": True,
        "signature_sha256": _contract._sha256(sig_path.read_bytes()),
        "contract_sha256": sig["contract_sha"],
        "manifest_sha256": sig["manifest_sha"],
    }


def _write_contract_check(contract_dir: Path, *, include_signature: bool = True) -> None:
    """Write a valid contract-check.json beside the contract file."""
    import hashlib
    contract_path = contract_dir / "contract.json"
    sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    schema_v = json.loads(contract_path.read_text()).get("schema_version", 2)
    artifact = {
        "contract_sha256": sha,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": schema_v,
        "result": "pass",
    }
    if include_signature:
        artifact["pm_signature"] = _signature_status(contract_dir)
    (contract_dir / "contract-check.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    )


def _write_preflight(repo_root: Path, phase: int, *,
                     head_sha: str | None = None,
                     generated_ts: str | None = None) -> Path:
    """Write a valid preflight artifact for the given phase."""
    if head_sha is None:
        try:
            head_sha = subprocess.check_output(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
            ).strip()
        except subprocess.CalledProcessError:
            head_sha = "a" * 40
    if generated_ts is None:
        generated_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    preflight_dir = repo_root / ".planning" / "auto-pilot" / "preflight"
    preflight_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "repo_root": str(repo_root),
        "branch": "feat/test",
        "head_sha": head_sha,
        "worktree_clean": True,
        "expected_gh_user": "Sewhoan",
        "actual_gh_user": "Sewhoan",
        "tool_versions": {"python3": "3.13.0", "git": "2.45.0", "codex": None, "claude": None},
        "generated_ts": generated_ts,
        "phase": phase,
    }
    path = preflight_dir / f"phase-{phase}.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return path




class TestDispatchContractCheck:
    def test_writes_pass_artifact(self, in_tmp_cwd, tmp_path):
        import orchestrator
        contract_dir = _make_contract_dir(tmp_path)
        contract_path = contract_dir / "contract.json"
        rc = orchestrator.main([
            "dispatch-contract-check", "--contract", str(contract_path)
        ])
        assert rc == 0
        artifact_path = contract_dir / "contract-check.json"
        assert artifact_path.exists()
        artifact = json.loads(artifact_path.read_text())
        assert artifact["result"] == "pass"
        assert len(artifact["contract_sha256"]) == 64
        assert "checked_at" in artifact
        assert artifact["schema_version"] == 2
        sig = artifact["pm_signature"]
        assert sig["verified"] is True
        assert len(sig["signature_sha256"]) == 64
        assert sig["contract_sha256"] == artifact["contract_sha256"]
        assert len(sig["manifest_sha256"]) == 64

    def test_missing_signature_returns_1_without_pass_artifact(self, in_tmp_cwd, tmp_path):
        import orchestrator
        contract_dir = _make_contract_dir(tmp_path)
        (contract_dir / "PM-SIGNATURE").unlink()
        rc = orchestrator.main([
            "dispatch-contract-check", "--contract", str(contract_dir / "contract.json")
        ])
        assert rc == 1
        assert not (contract_dir / "contract-check.json").exists()

    def test_missing_contract_returns_2(self, in_tmp_cwd, tmp_path):
        import orchestrator
        rc = orchestrator.main([
            "dispatch-contract-check", "--contract", str(tmp_path / "nope.json")
        ])
        assert rc == 2

    def test_invalid_contract_returns_1(self, in_tmp_cwd, tmp_path):
        import orchestrator
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"schema_version": 2}))  # missing required fields
        rc = orchestrator.main([
            "dispatch-contract-check", "--contract", str(bad)
        ])
        assert rc == 1

    def test_layer2_gate_missing_artifact(self, tmp_path):
        import _dispatch
        contract_dir = _make_contract_dir(tmp_path)
        with pytest.raises(_dispatch.ContractCheckMissing, match="missing"):
            _dispatch.prepare_subagent_ticket(
                contract_dir=contract_dir,
                worktree=tmp_path / "wt",
                subagent_role="worker",
                skip_preflight=True,
                # skip_contract_check=False (default)
            )

    def test_layer2_gate_stale_sha(self, tmp_path):
        import _dispatch
        contract_dir = _make_contract_dir(tmp_path)
        # Write a contract-check with wrong sha
        (contract_dir / "contract-check.json").write_text(json.dumps({
            "contract_sha256": "a" * 64,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "schema_version": 2,
            "result": "pass",
        }) + "\n")
        with pytest.raises(_dispatch.ContractCheckMissing, match="modified"):
            _dispatch.prepare_subagent_ticket(
                contract_dir=contract_dir,
                worktree=tmp_path / "wt",
                subagent_role="worker",
                skip_preflight=True,
            )

    def test_layer2_gate_legacy_artifact_missing_signature_status(self, tmp_path):
        import _dispatch
        contract_dir = _make_contract_dir(tmp_path)
        _write_contract_check(contract_dir, include_signature=False)
        with pytest.raises(_dispatch.ContractCheckMissing, match="PM-SIGNATURE status"):
            _dispatch.prepare_subagent_ticket(
                contract_dir=contract_dir,
                worktree=tmp_path / "wt",
                subagent_role="worker",
                skip_preflight=True,
            )

    def test_layer2_gate_stale_signature_status(self, tmp_path):
        import _dispatch
        contract_dir = _make_contract_dir(tmp_path)
        _write_contract_check(contract_dir)
        sig_path = contract_dir / "PM-SIGNATURE"
        sig = json.loads(sig_path.read_text())
        sig["run_id"] = "tampered-after-check"
        sig_path.write_text(json.dumps(sig) + "\n")
        with pytest.raises(_dispatch.ContractCheckMissing, match="PM-SIGNATURE modified"):
            _dispatch.prepare_subagent_ticket(
                contract_dir=contract_dir,
                worktree=tmp_path / "wt",
                subagent_role="worker",
                skip_preflight=True,
            )

    def test_layer2_gate_passes_with_valid_artifact(self, tmp_path):
        import _dispatch
        contract_dir = _make_contract_dir(tmp_path)
        _write_contract_check(contract_dir)
        # Should not raise ContractCheckMissing; preflight still gated
        with pytest.raises(_dispatch.PreflightError):
            _dispatch.prepare_subagent_ticket(
                contract_dir=contract_dir,
                worktree=tmp_path / "wt",
                subagent_role="worker",
            )


class TestPreflightGate:
    def test_missing_preflight_raises(self, tmp_path):
        import _dispatch
        contract_dir = _make_contract_dir(tmp_path)
        _write_contract_check(contract_dir)
        with pytest.raises(_dispatch.PreflightError, match="missing"):
            _dispatch.prepare_subagent_ticket(
                contract_dir=contract_dir,
                worktree=tmp_path / "wt",
                subagent_role="worker",
            )

    def test_stale_preflight_raises(self, tmp_path):
        import _dispatch
        contract_dir = _make_contract_dir(tmp_path)
        _write_contract_check(contract_dir)
        # Write preflight with old timestamp (> 900 s ago)
        old_ts = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat(timespec="seconds")
        # use contract_dir as repo_root heuristic: place .planning relative to it
        # The gate walks up from contract_dir to find .planning → use tmp_path
        _write_preflight(tmp_path, phase=1, generated_ts=old_ts)
        with pytest.raises(_dispatch.PreflightError, match="old"):
            _dispatch.prepare_subagent_ticket(
                contract_dir=contract_dir,
                worktree=tmp_path / "wt",
                subagent_role="worker",
            )

    def test_wrong_phase_preflight_raises(self, tmp_path):
        import _dispatch
        contract_dir = _make_contract_dir(tmp_path)
        _write_contract_check(contract_dir)
        # Write preflight for phase 99 but contract is phase 1
        _write_preflight(tmp_path, phase=99)
        # Now write the phase-1 artifact with wrong phase key
        preflight_dir = tmp_path / ".planning" / "auto-pilot" / "preflight"
        preflight_dir.mkdir(parents=True, exist_ok=True)
        bad = {
            "repo_root": str(tmp_path),
            "branch": "feat/test",
            "head_sha": "a" * 40,
            "worktree_clean": True,
            "expected_gh_user": "Sewhoan",
            "actual_gh_user": "Sewhoan",
            "tool_versions": {"python3": "3.13", "git": "2.45", "codex": None, "claude": None},
            "generated_ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "phase": 99,  # wrong phase for contract phase=1
        }
        (preflight_dir / "phase-1.json").write_text(json.dumps(bad) + "\n")
        with pytest.raises(_dispatch.PreflightError, match="mismatch"):
            _dispatch.prepare_subagent_ticket(
                contract_dir=contract_dir,
                worktree=tmp_path / "wt",
                subagent_role="worker",
            )

    def test_wrong_head_sha_preflight_raises(self, tmp_path):
        """Wrong head_sha triggers PreflightError when git is available in repo root."""
        import _dispatch
        # Set up a git repo in tmp_path so .git exists there
        subprocess.run(["git", "-C", str(tmp_path), "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
        (tmp_path / "a.txt").write_text("x\n")
        subprocess.run(["git", "-C", str(tmp_path), "add", "a.txt"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)
        subprocess.check_output(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
        ).strip()

        contract_dir = _make_contract_dir(tmp_path)
        _write_contract_check(contract_dir)
        # Write preflight with wrong head_sha
        _write_preflight(tmp_path, phase=1, head_sha="b" * 40)
        # b*40 != real_head → should raise
        with pytest.raises(_dispatch.PreflightError, match="mismatch"):
            _dispatch.prepare_subagent_ticket(
                contract_dir=contract_dir,
                worktree=tmp_path / "wt",
                subagent_role="worker",
            )

    def test_valid_preflight_allows_dispatch(self, tmp_path):
        """All gates pass → ticket is written successfully."""
        import _dispatch
        # Set up a git repo so HEAD check works
        subprocess.run(["git", "-C", str(tmp_path), "init", "-q", "-b", "main"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
        (tmp_path / "a.txt").write_text("x\n")
        subprocess.run(["git", "-C", str(tmp_path), "add", "a.txt"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)
        real_head = subprocess.check_output(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
        ).strip()

        contract_dir = _make_contract_dir(tmp_path)
        _write_contract_check(contract_dir)
        _write_preflight(tmp_path, phase=1, head_sha=real_head)

        worktree = tmp_path / "wt"
        worktree.mkdir()
        ticket = _dispatch.prepare_subagent_ticket(
            contract_dir=contract_dir,
            worktree=worktree,
            subagent_role="worker",
        )
        assert ticket.exists()
