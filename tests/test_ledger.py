"""Tests for scripts/_ledger.py — routing ledger IO, record derivation, and phase wiring.

Covers: load/validate/save IO, build_record derivation, append_phase_records,
p0_escaped auto-derive, idempotency, layout, orchestrator integration.
Rule-engine tests (evaluate_rebalance, normalize_model_token, ts comparison)
live in tests/test_rebalance.py.

Shared helpers (seed_ledger, ledger_record) live in conftest.py.
Style mirrors tests/test_routing.py: sys.path.insert, direct module import,
tmp_path fixtures, parametrize for near-miss coverage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _ledger  # noqa: E402

from conftest import ledger_record as _record, seed_ledger as _seed_ledger  # noqa: E402


# ---------------------------------------------------------------------------
# Round-dir builder (IO-heavy helper; lives here, not in conftest)
# ---------------------------------------------------------------------------

def _make_round_dir(
    tmp_path: Path,
    contract_id: str = "iter-1/phase-1/contract-1/round-1",
    claude_verdict: str = "APPROVE",
    codex_verdict: str = "APPROVE",
    claude_findings: list[dict[str, Any]] | None = None,
    codex_findings: list[dict[str, Any]] | None = None,
    worker_gates_first_try: bool | None = None,
) -> Path:
    # Build a minimal round-dir that build_record_from_round_dirs can read.
    # F-A fix: contract.json lives in the round dir, not the contract-K parent.
    round_dir = tmp_path / contract_id
    round_dir.mkdir(parents=True, exist_ok=True)
    contract_dir = round_dir.parent
    (round_dir / "contract.json").write_text(json.dumps({
        "id": contract_dir.name,
        "schema_version": 1,
        "title": "test",
        "spec_path": "docs/specs/test.md",
        "scope_files": ["src/foo.py"],
        "acceptance": "tests pass",
        "why": "test",
        "snapshot_shas": {"spec": "abc", "claude_md_chain": []},
        "context_bundle_path": str(contract_dir / "context-bundle"),
    }))

    def _review(verdict: str, findings: list[dict[str, Any]] | None) -> dict[str, Any]:
        return {
            "verdict": verdict,
            "contract_id": contract_dir.name,
            "scope_check": "OK",
            "findings": findings or [],
            "summary": "test",
        }

    outputs = round_dir / "outputs"
    for role, verdict, findings in [
        ("claude-reviewer", claude_verdict, claude_findings),
        ("codex-reviewer", codex_verdict, codex_findings),
    ]:
        role_dir = outputs / role
        role_dir.mkdir(parents=True, exist_ok=True)
        (role_dir / "review.json").write_text(json.dumps(_review(verdict, findings)))

    if worker_gates_first_try is not None:
        worker_dir = outputs / "worker"
        worker_dir.mkdir(parents=True, exist_ok=True)
        (worker_dir / "status.json").write_text(json.dumps({
            "gates_first_try": worker_gates_first_try,
        }))

    return round_dir


# ---------------------------------------------------------------------------
# load_ledger
# ---------------------------------------------------------------------------

class TestLoadLedger:
    def test_missing_file_returns_skeleton(self, tmp_path: Path) -> None:
        data = _ledger.load_ledger(tmp_path / "ledger.yaml")
        assert data["schema_version"] == 1
        assert data["records"] == []
        assert data["rebalance_log"] == []

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.yaml"
        path.write_text(":\n  bad: [unclosed\n")
        with pytest.raises(_ledger.LedgerError):
            _ledger.load_ledger(path)

    def test_non_mapping_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.yaml"
        path.write_text("- just\n- a list\n")
        with pytest.raises(_ledger.LedgerError):
            _ledger.load_ledger(path)


# ---------------------------------------------------------------------------
# validate_ledger
# ---------------------------------------------------------------------------

class TestValidateLedger:
    def test_accepts_seed_shape(self) -> None:
        _ledger.validate_ledger(_seed_ledger())

    def test_accepts_record_with_p0_escaped(self) -> None:
        data = _seed_ledger()
        data["records"].append(_record(p0_escaped=True))
        _ledger.validate_ledger(data)

    def test_rejects_missing_schema_version(self) -> None:
        data = _seed_ledger()
        del data["schema_version"]
        with pytest.raises(_ledger.LedgerError):
            _ledger.validate_ledger(data)

    def test_rejects_bad_task_class(self) -> None:
        data = _seed_ledger()
        r = _record()
        r["task_class"] = "not-a-valid-class"
        data["records"].append(r)
        with pytest.raises(_ledger.LedgerError):
            _ledger.validate_ledger(data)

    def test_rejects_record_missing_outcome(self) -> None:
        data = _seed_ledger()
        r = _record()
        del r["outcome"]
        data["records"].append(r)
        with pytest.raises(_ledger.LedgerError):
            _ledger.validate_ledger(data)

    def test_validate_called_before_evaluate_rebalance(self, tmp_path: Path) -> None:
        # F11: orchestrator calls validate_ledger before evaluate_rebalance.
        import orchestrator
        import yaml
        ledger_path = tmp_path / ".claude" / "routing" / "ledger.yaml"
        ledger_path.parent.mkdir(parents=True)
        ledger_path.write_text(yaml.safe_dump({"schema_version": 99}))

        class _FakeArgs:
            project_root = str(tmp_path)
            apply = False

        rc = orchestrator.cmd_ledger_rebalance(_FakeArgs())
        assert rc != 0


# ---------------------------------------------------------------------------
# save_ledger / round-trip
# ---------------------------------------------------------------------------

class TestSaveLedger:
    def test_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.yaml"
        data = _seed_ledger()
        data["records"].append(_record(task_id="x1"))
        _ledger.save_ledger(path, data)
        assert _ledger.load_ledger(path)["records"][0]["task_id"] == "x1"

    def test_save_invalid_data_raises(self, tmp_path: Path) -> None:
        with pytest.raises(_ledger.LedgerError):
            _ledger.save_ledger(tmp_path / "l.yaml", {"schema_version": 99})

    def test_atomic_write_creates_parent(self, tmp_path: Path) -> None:
        path = tmp_path / "routing" / "ledger.yaml"
        _ledger.save_ledger(path, _seed_ledger())
        assert path.exists()


# ---------------------------------------------------------------------------
# build_record_from_round_dirs
# ---------------------------------------------------------------------------

class TestBuildRecord:
    def test_basic_approve_record(self, tmp_path: Path) -> None:
        round_dir = _make_round_dir(tmp_path)
        rec = _ledger.build_record_from_round_dirs(round_dir.parent, [round_dir])
        assert rec["task_id"] == round_dir.parent.name
        assert rec["outcome"]["review_rounds"] == 1
        assert rec["outcome"]["rejects_real"] == 0

    def test_reject_with_p0_counts_as_real(self, tmp_path: Path) -> None:
        rd = _make_round_dir(tmp_path, claude_verdict="REJECT",
                             claude_findings=[{"severity": "P0", "file": "x.py",
                                               "line": 1, "message": "bad"}])
        assert _ledger.build_record_from_round_dirs(
            rd.parent, [rd])["outcome"]["rejects_real"] >= 1

    def test_reject_with_only_p2_counts_as_false(self, tmp_path: Path) -> None:
        rd = _make_round_dir(tmp_path, claude_verdict="REJECT",
                             claude_findings=[{"severity": "P2", "file": "x.py",
                                               "line": 1, "message": "nit"}],
                             contract_id="iter-1/phase-1/contract-2/round-1")
        rec = _ledger.build_record_from_round_dirs(rd.parent, [rd])
        assert rec["outcome"]["rejects_real"] == 0
        assert rec["outcome"].get("rejects_false", 0) >= 1

    def test_abstain_final_round_sets_abstained(self, tmp_path: Path) -> None:
        rd = _make_round_dir(tmp_path, codex_verdict="ABSTAIN",
                             contract_id="iter-1/phase-1/contract-3/round-1")
        assert _ledger.build_record_from_round_dirs(
            rd.parent, [rd])["outcome"]["abstained"] is True

    def test_gates_first_try_from_worker_status(self, tmp_path: Path) -> None:
        rd = _make_round_dir(tmp_path, worker_gates_first_try=False,
                             contract_id="iter-1/phase-1/contract-4/round-1")
        assert _ledger.build_record_from_round_dirs(
            rd.parent, [rd])["outcome"]["gates_first_try"] is False

    def test_gates_first_try_inferred_from_review_rounds(self, tmp_path: Path) -> None:
        rd = _make_round_dir(tmp_path, contract_id="iter-1/phase-1/contract-5/round-1")
        rec = _ledger.build_record_from_round_dirs(rd.parent, [rd])
        assert rec["outcome"]["gates_first_try"] is True
        assert "gates_first_try inferred" in rec.get("notes", "")

    def test_p0_escaped_auto_derived_from_p0_finding(self, tmp_path: Path) -> None:
        # F4: p0_escaped set when any review carries a P0 finding.
        rd = _make_round_dir(tmp_path, claude_verdict="APPROVE",
                             claude_findings=[{"severity": "P0", "file": "x.py",
                                               "line": 1, "message": "escaping P0"}],
                             contract_id="iter-1/phase-1/contract-6/round-1")
        assert _ledger.build_record_from_round_dirs(
            rd.parent, [rd])["outcome"].get("p0_escaped") is True

    def test_multi_round_aggregates_all_rounds(self, tmp_path: Path) -> None:
        # F3: all round-* dirs must be passed; both rounds aggregated.
        base = "iter-1/phase-1/contract-7"
        r1 = _make_round_dir(tmp_path, contract_id=f"{base}/round-1",
                             claude_verdict="REJECT",
                             claude_findings=[{"severity": "P1", "file": "x.py",
                                               "line": 1, "message": "bad"}])
        r2 = _make_round_dir(tmp_path, contract_id=f"{base}/round-2",
                             claude_verdict="APPROVE")
        rec = _ledger.build_record_from_round_dirs(r1.parent, [r1, r2])
        assert rec["outcome"]["review_rounds"] == 2
        assert rec["outcome"]["rejects_real"] >= 1

    def test_contract_json_read_from_round_dir(self, tmp_path: Path) -> None:
        # F-A: contract.json in round dir, not contract parent.
        rd = _make_round_dir(tmp_path, contract_id="iter-1/phase-1/contract-9/round-1")
        assert (rd / "contract.json").exists()
        assert not (rd.parent / "contract.json").exists()
        assert "task_id" in _ledger.build_record_from_round_dirs(rd.parent, [rd])

    def test_worker_model_field_used(self, tmp_path: Path) -> None:
        # F-B: contract uses worker_model field; role/task_class always defaulted.
        rd = _make_round_dir(tmp_path, contract_id="iter-1/phase-1/contract-10/round-1")
        (rd / "contract.json").write_text(json.dumps(
            {"id": "contract-10", "worker_model": "opus", "schema_version": 1}
        ))
        rec = _ledger.build_record_from_round_dirs(rd.parent, [rd])
        assert rec["model"] == "opus"
        assert "role defaulted" in rec.get("notes", "")
        assert "task_class defaulted" in rec.get("notes", "")


# ---------------------------------------------------------------------------
# append_phase_records — idempotency and multi-round (F1/F3)
# ---------------------------------------------------------------------------

class TestAppendPhaseRecords:
    def test_append_returns_count(self, tmp_path: Path) -> None:
        contracts_root = tmp_path / "contracts"
        _make_round_dir(contracts_root, contract_id="iter-1/phase-1/contract-1/round-1")
        project_root = tmp_path / "project"
        project_root.mkdir()
        assert _ledger.append_phase_records(project_root, contracts_root) == 1

    def test_idempotent_rerun_appends_zero(self, tmp_path: Path) -> None:
        contracts_root = tmp_path / "contracts"
        _make_round_dir(contracts_root, contract_id="iter-1/phase-1/contract-1/round-1")
        project_root = tmp_path / "project"
        project_root.mkdir()
        _ledger.append_phase_records(project_root, contracts_root)
        assert _ledger.append_phase_records(project_root, contracts_root) == 0

    def test_duplicate_task_id_warns_on_stderr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # P2: duplicate skip must warn on stderr with id hint.
        contracts_root = tmp_path / "contracts"
        _make_round_dir(contracts_root, contract_id="iter-1/phase-1/contract-1/round-1")
        project_root = tmp_path / "project"
        project_root.mkdir()
        _ledger.append_phase_records(project_root, contracts_root)
        capsys.readouterr()
        assert _ledger.append_phase_records(project_root, contracts_root) == 0
        err = capsys.readouterr().err
        assert "duplicate task_id" in err
        assert "'contract-1'" in err
        assert "contract.json" in err

    def test_empty_contracts_root_appends_zero(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        assert _ledger.append_phase_records(project_root, tmp_path / "contracts") == 0

    def test_all_rounds_aggregated_f1_f3(self, tmp_path: Path) -> None:
        # F1/F3: both rounds must be aggregated, not just the latest.
        contracts_root = tmp_path / "contracts"
        base = "iter-1/phase-1/contract-1"
        _make_round_dir(contracts_root, contract_id=f"{base}/round-1",
                        claude_verdict="REJECT",
                        claude_findings=[{"severity": "P1", "file": "x.py",
                                          "line": 1, "message": "bad"}])
        _make_round_dir(contracts_root, contract_id=f"{base}/round-2",
                        claude_verdict="APPROVE")
        project_root = tmp_path / "project"
        project_root.mkdir()
        assert _ledger.append_phase_records(project_root, contracts_root) == 1
        import yaml
        ledger = yaml.safe_load(
            (project_root / ".claude" / "routing" / "ledger.yaml").read_text()
        )
        rec = ledger["records"][0]
        assert rec["outcome"]["review_rounds"] == 2
        assert rec["outcome"]["rejects_real"] >= 1


# ---------------------------------------------------------------------------
# F-C: --project-root contracts path
# ---------------------------------------------------------------------------

class TestLedgerAppendProjectRoot:
    def test_non_cwd_project_root_reads_contracts_there(self, tmp_path: Path) -> None:
        # F-C: contracts_root derived from project_root, not cwd.
        import orchestrator
        import yaml

        project_root = tmp_path / "myproject"
        project_root.mkdir()
        contracts_root = project_root / ".planning" / "auto-pilot" / "contracts"
        _make_round_dir(contracts_root, contract_id="iter-1/phase-1/contract-1/round-1")

        class _FakeArgs:
            project_root = str(tmp_path / "myproject")

        rc = orchestrator.cmd_ledger_append(_FakeArgs())
        assert rc == 0
        ledger = yaml.safe_load(
            (project_root / ".claude" / "routing" / "ledger.yaml").read_text()
        )
        assert len(ledger["records"]) == 1


# ---------------------------------------------------------------------------
# orchestrator: ledger-rebalance --apply IO failure
# ---------------------------------------------------------------------------

class TestRebalanceApplySaveFailure:
    def test_apply_save_oserror_returns_2(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # P1: OSError on save must return rc=2, not an uncaught traceback.
        import orchestrator

        proposal = {
            "ts": "2026-06-12T00:00:00+00:00",
            "role": "worker-primary",
            "task_class": "feature-multi-file",
            "from_model": "sonnet",
            "to_model": "opus",
            "rule": "promote-2x-gate-fail",
            "evidence": ["t1", "t2"],
        }
        monkeypatch.setattr(_ledger, "evaluate_rebalance", lambda *_a, **_k: [proposal])

        def _disk_full(*_a: Any, **_k: Any) -> None:
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(_ledger, "save_ledger", _disk_full)

        class _FakeArgs:
            project_root = str(tmp_path)
            apply = True

        rc = orchestrator.cmd_ledger_rebalance(_FakeArgs())
        assert rc == 2
        err = capsys.readouterr().err
        assert "ledger-rebalance --apply save failed" in err
        assert "No space left on device" in err


# ---------------------------------------------------------------------------
# orchestrator: ledger failure does not block phase-end
# ---------------------------------------------------------------------------

class TestPhaseEndLedgerNonBlocking:
    def test_ledger_failure_does_not_block_phase_end(
        self, in_tmp_cwd: Path, sample_spec: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """append_phase_records raising any exception must not block phase-end."""
        import orchestrator

        def _run(argv: list[str]) -> int:
            return orchestrator.main(argv)

        _run(["init", "--spec", str(sample_spec), "--max-workers", "4"])
        _run(["phase-start", "--phase", "1", "--contracts", "1"])
        def _bad_append(*_a: Any, **_k: Any) -> None:
            raise RuntimeError("simulated ledger failure")

        monkeypatch.setattr(_ledger, "append_phase_records", _bad_append)
        monkeypatch.setenv("AUTO_PILOT_SKIP_EVIDENCE", "1")
        rc = _run(["phase-end", "--phase", "1", "--status", "success"])
        assert rc == 0
