"""Tests for β contract schema items (round-2 W2):
  ⓓ-7  contract schema v2 (new required fields + project_context)
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
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


def _write_contract_check(contract_dir: Path) -> None:
    """Write a valid contract-check.json beside the contract file."""
    import _contract
    contract_path = contract_dir / "contract.json"
    sig_path = contract_dir / "PM-SIGNATURE"
    sig = json.loads(sig_path.read_text())
    sha = _contract._sha256(contract_path.read_bytes())
    schema_v = json.loads(contract_path.read_text()).get("schema_version", 2)
    artifact = {
        "contract_sha256": sha,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": schema_v,
        "result": "pass",
        "pm_signature": {
            "verified": True,
            "signature_sha256": _contract._sha256(sig_path.read_bytes()),
            "contract_sha256": sig["contract_sha"],
            "manifest_sha256": sig["manifest_sha"],
        },
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


SCHEMA_PATH = ROOT / "schemas" / "contract.schema.json"
PREFLIGHT_SCHEMA_PATH = ROOT / "schemas" / "preflight.schema.json"


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
