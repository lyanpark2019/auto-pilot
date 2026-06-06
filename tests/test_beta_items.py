"""Tests for β build-worker items (round-2 W2):
  ⓓ-6  reviewer watchdog (soft-warn, hard-kill + retry, retry-fail)
  ⓓ-7  contract schema v2 (new required fields + project_context)
  ⓓ-7② dispatch-contract-check subcommand + layer-2 gate
  ⓓ-9  pm_preflight.sh + preflight gate in prepare_subagent_ticket
  ⓗ    round-budget subcommand
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURE = ROOT / "tests" / "fixtures" / "contracts" / "sample_contract.json"
SCHEMA_PATH = ROOT / "schemas" / "contract.schema.json"
PREFLIGHT_SCHEMA_PATH = ROOT / "schemas" / "preflight.schema.json"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

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


def _write_contract_check(contract_dir: Path) -> None:
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


# ─────────────────────────────────────────────────────────────────────────────
# ⓓ-7  Contract schema v2
# ─────────────────────────────────────────────────────────────────────────────

class TestContractSchemaV2:
    def test_schema_version_must_be_2(self):
        import jsonschema
        schema = json.loads(SCHEMA_PATH.read_text())
        data = json.loads(FIXTURE.read_text())
        # v2 fixture validates
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(data)

    def test_schema_version_1_rejected(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        data["schema_version"] = 1
        with pytest.raises(_contract.ContractValidationError):
            _contract.validate(data)

    def test_missing_target_repo_rejected(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        del data["target_repo"]
        with pytest.raises(_contract.ContractValidationError):
            _contract.validate(data)

    def test_missing_target_layer_rejected(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        del data["target_layer"]
        with pytest.raises(_contract.ContractValidationError):
            _contract.validate(data)

    def test_invalid_target_layer_rejected(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        data["target_layer"] = "database"  # not in enum
        with pytest.raises(_contract.ContractValidationError):
            _contract.validate(data)

    def test_missing_hard_constraints_rejected(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        del data["hard_constraints"]
        with pytest.raises(_contract.ContractValidationError):
            _contract.validate(data)

    def test_empty_hard_constraints_rejected(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        data["hard_constraints"] = []  # minItems 1
        with pytest.raises(_contract.ContractValidationError):
            _contract.validate(data)

    def test_target_layer_enum_values(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        for layer in ("API", "BFF", "frontend", "worker", "plugin"):
            data["target_layer"] = layer
            _contract.validate(data)  # must not raise

    def test_pattern_refs_optional(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        assert "pattern_refs" not in data
        _contract.validate(data)  # no pattern_refs is valid

    def test_pattern_refs_accepted_when_present(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        data["pattern_refs"] = ["scripts/_contract.py:atomic_write_text"]
        _contract.validate(data)

    def test_project_context_optional_in_snapshot_shas(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        assert "project_context" not in data["snapshot_shas"]
        _contract.validate(data)

    def test_project_context_accepted_when_hex64(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        data["snapshot_shas"]["project_context"] = "c" * 64
        _contract.validate(data)

    def test_project_context_rejected_when_wrong_length(self):
        import _contract
        data = json.loads(FIXTURE.read_text())
        data["snapshot_shas"]["project_context"] = "c" * 63  # too short
        with pytest.raises(_contract.ContractValidationError):
            _contract.validate(data)


class TestSnapshotContextProjectContext:
    def test_snapshot_context_without_project_context(self, tmp_path):
        import _contract
        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n")
        dest = tmp_path / "out"
        dest.mkdir()
        shas = _contract.snapshot_context(dest, spec, [])
        assert shas.project_context is None
        assert not (dest / "context-bundle" / "project-context.md").exists()

    def test_snapshot_context_with_project_context(self, tmp_path):
        import _contract
        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n")
        ctx = tmp_path / "graph.md"
        ctx.write_text("# graph\nnodes: 100\n")
        dest = tmp_path / "out"
        dest.mkdir()
        shas = _contract.snapshot_context(dest, spec, [], project_context_path=ctx)
        assert shas.project_context is not None
        assert len(shas.project_context) == 64
        assert (dest / "context-bundle" / "project-context.md").exists()
        manifest = (dest / "context-bundle" / "MANIFEST.txt").read_text()
        assert "project-context.md" in manifest

    def test_verify_snapshots_context_blind_logs(self, tmp_path, capsys):
        import _contract
        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n")
        dest = tmp_path / "contract"
        dest.mkdir()
        shas = _contract.snapshot_context(dest, spec, [])
        data = json.loads(FIXTURE.read_text())
        data["snapshot_shas"]["spec"] = shas.spec
        data["snapshot_shas"]["claude_md_chain"] = []
        data["context_bundle_path"] = str(dest / "context-bundle")
        _contract.write_contract(data, dest / "contract.json")
        _contract.verify_snapshots(dest)
        captured = capsys.readouterr()
        assert "context-blind" in captured.err

    def test_verify_snapshots_project_context_tamper(self, tmp_path):
        import _contract
        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n")
        ctx = tmp_path / "ctx.md"
        ctx.write_text("original context\n")
        dest = tmp_path / "contract"
        dest.mkdir()
        shas = _contract.snapshot_context(dest, spec, [], project_context_path=ctx)
        data = json.loads(FIXTURE.read_text())
        data["snapshot_shas"]["spec"] = shas.spec
        data["snapshot_shas"]["claude_md_chain"] = []
        data["snapshot_shas"]["project_context"] = shas.project_context
        data["context_bundle_path"] = str(dest / "context-bundle")
        _contract.write_contract(data, dest / "contract.json")
        # Tamper
        (dest / "context-bundle" / "project-context.md").write_text("tampered\n")
        with pytest.raises(_contract.SnapshotMismatchError, match="project-context"):
            _contract.verify_snapshots(dest)

    def test_verify_snapshots_project_context_declared_but_absent(self, tmp_path):
        import _contract
        spec = tmp_path / "spec.md"
        spec.write_text("# spec\n")
        dest = tmp_path / "contract"
        dest.mkdir()
        shas = _contract.snapshot_context(dest, spec, [])
        data = json.loads(FIXTURE.read_text())
        data["snapshot_shas"]["spec"] = shas.spec
        data["snapshot_shas"]["claude_md_chain"] = []
        data["snapshot_shas"]["project_context"] = "d" * 64  # declared but no file
        data["context_bundle_path"] = str(dest / "context-bundle")
        _contract.write_contract(data, dest / "contract.json")
        with pytest.raises(_contract.SnapshotMismatchError, match="absent"):
            _contract.verify_snapshots(dest)


# ─────────────────────────────────────────────────────────────────────────────
# ⓓ-7②  dispatch-contract-check (orchestrator subcommand + layer-2 gate)
# ─────────────────────────────────────────────────────────────────────────────

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
        import _dispatch, _contract
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


# ─────────────────────────────────────────────────────────────────────────────
# ⓓ-9  preflight gate
# ─────────────────────────────────────────────────────────────────────────────

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
        real_head = subprocess.check_output(
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


class TestPreflightSchema:
    def test_schema_is_valid_jsonschema(self):
        import jsonschema
        schema = json.loads(PREFLIGHT_SCHEMA_PATH.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)

    def test_valid_artifact_validates(self, tmp_path):
        import jsonschema
        schema = json.loads(PREFLIGHT_SCHEMA_PATH.read_text())
        artifact = {
            "repo_root": "/workspace/repo",
            "branch": "main",
            "head_sha": "a" * 40,
            "worktree_clean": True,
            "expected_gh_user": "Sewhoan",
            "actual_gh_user": "Sewhoan",
            "tool_versions": {"python3": "3.13.0", "git": "2.45.0", "codex": None, "claude": "0.7.0"},
            "generated_ts": "2026-06-06T12:00:00+00:00",
            "phase": 1,
        }
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(artifact)

    def test_missing_required_field_rejected(self, tmp_path):
        import jsonschema
        schema = json.loads(PREFLIGHT_SCHEMA_PATH.read_text())
        artifact = {
            "repo_root": "/workspace/repo",
            "branch": "main",
            # head_sha missing
            "worktree_clean": True,
            "expected_gh_user": "Sewhoan",
            "actual_gh_user": "Sewhoan",
            "tool_versions": {"python3": "3.13.0", "git": "2.45.0"},
            "generated_ts": "2026-06-06T12:00:00+00:00",
            "phase": 1,
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(artifact)

    def test_pm_preflight_sh_syntax(self):
        """bash -n must report no syntax errors."""
        result = subprocess.run(
            ["bash", "-n", str(ROOT / "scripts" / "pm_preflight.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"bash -n failed: {result.stderr}"


# ─────────────────────────────────────────────────────────────────────────────
# ⓓ-6  Reviewer watchdog (real subprocess-based tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestReviewerWatchdog:
    """Three paths tested with real subprocesses (sleep-based stand-ins)."""

    def _make_handle(self, role: str, tmp_path: Path,
                     cmd: list[str]) -> "object":
        """Spawn a real subprocess and return a SpawnHandle-like object."""
        import _reviewer_wrapper as rw
        output_dir = tmp_path / role
        output_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(cmd)

        class _RealHandle:
            def __init__(self) -> None:
                self.role = role
                self.output_dir = output_dir
                self.proc = proc
                # Reconstruct spawn kwargs so _respawn can work
                self._spawn_kwargs: dict = {}

            def poll(self) -> int | None:
                return self.proc.poll()

        return _RealHandle()

    def test_soft_warn_fires_proc_finishes_no_kill(self, tmp_path):
        """Soft-warn fires, process finishes normally (no kill)."""
        import _reviewer_wrapper as rw

        output_dir = tmp_path / "r1"
        output_dir.mkdir()

        # Subprocess sleeps briefly then exits; soft_warn fires immediately (0s)
        # We can't actually wait for the real 300s soft-warn, so we override thresholds
        proc = subprocess.Popen(["sleep", "0.3"])

        class _Handle:
            role = "r1"
            _spawn_kwargs: dict = {}

            def __init__(self) -> None:
                self.output_dir = output_dir
                self.proc = proc

            def poll(self) -> int | None:
                return self.proc.poll()

        handle = _Handle()
        # Use soft_warn_sec=0 (fires immediately), hard_kill_sec=9999 (never fires)
        # Process will exit naturally (sleep 0.3) → write done.marker manually
        # Simulate: process exits without a marker → but soft-warn should have fired

        # Actually: we write the marker after a tiny delay to simulate the reviewer
        # completing after the soft-warn fires
        import threading

        def _write_marker() -> None:
            time.sleep(0.15)
            (output_dir / "done.marker").touch()

        t = threading.Thread(target=_write_marker, daemon=True)
        t.start()

        failures = rw.wait_all(
            [handle],
            timeout_sec=5,
            soft_warn_sec=0,       # fire immediately
            hard_kill_sec=9999,    # never kill
        )
        t.join(timeout=2)
        assert failures == []
        assert (output_dir / "done.marker").exists()

    def test_hard_kill_retry_succeeds(self, tmp_path):
        """Hard kill fires; retry spawns successfully and writes done.marker."""
        import _reviewer_wrapper as rw

        output_dir_orig = tmp_path / "r2"
        output_dir_orig.mkdir()

        # Long-running process that will be killed
        proc = subprocess.Popen(["sleep", "60"])
        # Capture kill calls
        killed: list[int] = []
        orig_kill = _reviewer_wrapper_kill_injector(proc)

        retry_output_dir = tmp_path / "r2-retry"
        retry_output_dir.mkdir()

        class _Handle:
            role = "r2"
            _spawn_kwargs: dict = {}

            def __init__(self) -> None:
                self.output_dir = output_dir_orig
                self.proc = proc

            def poll(self) -> int | None:
                return self.proc.poll()

        handle = _Handle()

        # Override _respawn to return a "success" handle
        import threading

        def _write_marker_delayed(path: Path) -> None:
            time.sleep(0.1)
            (path / "done.marker").touch()

        retry_thread = threading.Thread(
            target=_write_marker_delayed, args=(retry_output_dir,), daemon=True
        )

        original_respawn = rw._respawn

        def _fake_respawn(h: object) -> object:  # type: ignore[override]
            retry_thread.start()

            class _RetryHandle:
                role = "r2"
                _spawn_kwargs: dict = {}

                def __init__(self) -> None:
                    self.output_dir = retry_output_dir
                    self.proc = subprocess.Popen(["sleep", "0"])

                def poll(self) -> int | None:
                    return self.proc.poll()

            return _RetryHandle()

        rw._respawn = _fake_respawn
        try:
            failures = rw.wait_all(
                [handle],
                timeout_sec=10,
                soft_warn_sec=9999,   # no soft-warn
                hard_kill_sec=0,      # kill immediately
            )
        finally:
            rw._respawn = original_respawn
            proc.kill()
            proc.wait()

        assert failures == []  # retry succeeded
        retry_thread.join(timeout=2)

    def test_retry_fails_structured_failure_returned(self, tmp_path):
        """Hard kill; retry also fails → ReviewerFailure in return list."""
        import _reviewer_wrapper as rw

        output_dir_orig = tmp_path / "r3"
        output_dir_orig.mkdir()
        retry_output_dir = tmp_path / "r3-retry"
        retry_output_dir.mkdir()

        proc = subprocess.Popen(["sleep", "60"])

        class _Handle:
            role = "r3"
            _spawn_kwargs: dict = {}

            def __init__(self) -> None:
                self.output_dir = output_dir_orig
                self.proc = proc

            def poll(self) -> int | None:
                return self.proc.poll()

        handle = _Handle()

        original_respawn = rw._respawn

        def _fake_respawn_fail(h: object) -> object:  # type: ignore[override]
            # Retry exits immediately without marker
            retry_proc = subprocess.Popen(["sleep", "0"])

            class _RetryHandle:
                role = "r3"
                _spawn_kwargs: dict = {}

                def __init__(self) -> None:
                    self.output_dir = retry_output_dir
                    self.proc = retry_proc

                def poll(self) -> int | None:
                    return self.proc.poll()

            return _RetryHandle()

        rw._respawn = _fake_respawn_fail
        try:
            failures = rw.wait_all(
                [handle],
                timeout_sec=10,
                soft_warn_sec=9999,
                hard_kill_sec=0,      # kill immediately
            )
        finally:
            rw._respawn = original_respawn
            proc.kill()
            proc.wait()

        assert len(failures) == 1
        assert failures[0].role == "r3"
        assert "retry" in failures[0].reason


def _reviewer_wrapper_kill_injector(proc: subprocess.Popen) -> None:
    """Noop helper — real proc is used, just tracks side-effects."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# ⓗ  round-budget deterministic gate
# ─────────────────────────────────────────────────────────────────────────────

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
