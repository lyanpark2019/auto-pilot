"""Tests for scripts/_escalation_emit.py and the 3 emit-seam wiring points.

For each emit point the suite asserts BOTH:
  (a) side effect: a schema-valid escalation record is written with the correct
      problem_class.
  (b) control flow: the give-up path returns its original code / value / raises
      its original exception exactly as before.
Plus:
  RED isolation: when bump_or_create is patched to raise RuntimeError the
      give-up path still behaves identically.
  Byte-stability: _escalation_emit source contains no datetime.now / utcnow.
"""
from __future__ import annotations

import inspect
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _escalation
import _escalation_emit
import _improvement
import orchestrator
import _promotion
from _escalation import validate_escalation
from _escalation_emit import emit_escalation

NOW = datetime(2026, 6, 15, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_state(tmp_path: Path, *, run_id: str = "rTEST") -> None:
    planning = tmp_path / ".planning" / "auto-pilot"
    planning.mkdir(parents=True, exist_ok=True)
    (planning / "state.json").write_text(json.dumps({
        "status": "running",
        "run_id": run_id,
        "phases": [],
        "total_phases": 3,
        "max_workers": 4,
        "current_phase": 0,
    }))


def _find_escalation_files(ledger: Path) -> list[Path]:
    if not ledger.exists():
        return []
    return [p for p in ledger.glob("*.json") if not p.name.endswith(".lock")]


def _seed_promotion_ticket(ledger: Path, fp: str, *, all_gates: bool = False) -> None:
    ledger.mkdir(parents=True, exist_ok=True)
    gate: dict[str, Any] = {"tests_pass": False, "ci_pass": False, "user_approved": False}
    if all_gates:
        gate = {"tests_pass": True, "ci_pass": True, "user_approved": True}
    ticket = {
        "schema_version": 1,
        "fingerprint": fp,
        "pattern": "bare except swallows error",
        "source": "reviewer-finding",
        "candidate_asset": "hook",
        "state": "verified",
        "distinct_runs": 2,
        "occurrences": 3,
        "first_seen": "2026-06-10T00:00:00Z",
        "last_seen": "2026-06-15T00:00:00Z",
        "plugin_version": "0.8.9",
        "repo_fingerprint": "abc123",
        "promotion_gate": gate,
        "evidence": [{"run_id": "r1", "snippet": "bare-except-in-hook"}],
    }
    (ledger / f"{fp}.json").write_text(json.dumps(ticket, indent=2))


# ===========================================================================
# Byte-stability assertion
# ===========================================================================


def test_escalation_emit_source_has_no_datetime_now() -> None:
    """_escalation_emit must never call datetime.now() or datetime.utcnow()."""
    src = inspect.getsource(_escalation_emit)
    assert "datetime.now" not in src, "_escalation_emit must not call datetime.now"
    assert "datetime.utcnow" not in src, "_escalation_emit must not call datetime.utcnow"


# ===========================================================================
# Unit: emit_escalation wrapper
# ===========================================================================


class TestEmitEscalation:
    def test_writes_valid_record(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_escalation, "ledger_dir", lambda repo_root, commit_to: tmp_path)
        emit_escalation(
            problem_class="doom-loop",
            suggested_enrich_query="break repeated failure: abc123",
            approach="deterministic-retry",
            outcome="repeated-3-rounds",
            run_id="rTEST",
            snippet="phase-1 finding abc123 x3",
            repo_root=Path("."),
            now=NOW,
        )
        files = _find_escalation_files(tmp_path)
        assert len(files) == 1
        record = json.loads(files[0].read_text())
        validate_escalation(record)
        assert record["problem_class"] == "doom-loop"

    def test_never_raises_on_bump_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_escalation, "bump_or_create", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        # Should not raise
        emit_escalation(
            problem_class="doom-loop",
            suggested_enrich_query="break repeated failure: abc123",
            approach="deterministic-retry",
            outcome="repeated-3-rounds",
            run_id="rTEST",
            snippet="phase-1 finding abc123 x3",
            repo_root=Path("."),
            now=NOW,
        )

    def test_never_raises_on_whitespace_query(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_escalation, "ledger_dir", lambda repo_root, commit_to: tmp_path)
        # whitespace-only query raises ValueError in bump_or_create — must be swallowed
        emit_escalation(
            problem_class="doom-loop",
            suggested_enrich_query="   ",
            approach="deterministic-retry",
            outcome="repeated-3-rounds",
            run_id="rTEST",
            snippet="phase-1 finding abc123 x3",
            repo_root=Path("."),
            now=NOW,
        )


# ===========================================================================
# Emit point (a): doom-loop — orchestrator.cmd_pivot_check
# ===========================================================================


class TestEmitDoomLoop:
    def test_side_effect_escalation_written(
        self, in_tmp_cwd: Path, sample_spec: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(a) 3rd pivot-check hit writes a doom-loop escalation record."""
        escalation_ledger = in_tmp_cwd / "esc-ledger"
        monkeypatch.setattr(_escalation, "ledger_dir", lambda r, c: escalation_ledger)

        orchestrator.main(["init", "--spec", str(sample_spec)])
        orchestrator.main(["pivot-check", "--phase", "1", "--finding-hash", "h1"])
        orchestrator.main(["pivot-check", "--phase", "1", "--finding-hash", "h1"])
        orchestrator.main(["pivot-check", "--phase", "1", "--finding-hash", "h1"])

        files = _find_escalation_files(escalation_ledger)
        assert files, "doom-loop escalation record must be written on 3rd hit"
        record = json.loads(files[0].read_text())
        validate_escalation(record)
        assert record["problem_class"] == "doom-loop"

    def test_control_flow_returns_1(
        self, in_tmp_cwd: Path, sample_spec: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(b) return value is still 1 (pivot-needed) even with emit."""
        escalation_ledger = in_tmp_cwd / "esc-ledger"
        monkeypatch.setattr(_escalation, "ledger_dir", lambda r, c: escalation_ledger)

        orchestrator.main(["init", "--spec", str(sample_spec)])
        orchestrator.main(["pivot-check", "--phase", "1", "--finding-hash", "h1"])
        orchestrator.main(["pivot-check", "--phase", "1", "--finding-hash", "h1"])
        rc = orchestrator.main(["pivot-check", "--phase", "1", "--finding-hash", "h1"])
        assert rc == 1

    def test_red_isolation_emit_failure_does_not_change_return(
        self, in_tmp_cwd: Path, sample_spec: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED: bump_or_create throws RuntimeError → doom-loop still returns 1."""
        monkeypatch.setattr(
            _escalation, "bump_or_create",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        orchestrator.main(["init", "--spec", str(sample_spec)])
        orchestrator.main(["pivot-check", "--phase", "1", "--finding-hash", "h1"])
        orchestrator.main(["pivot-check", "--phase", "1", "--finding-hash", "h1"])
        rc = orchestrator.main(["pivot-check", "--phase", "1", "--finding-hash", "h1"])
        assert rc == 1


# ===========================================================================
# Emit point (b): promotion-gate-unmet — _promotion.cmd_improvements_set_state
# ===========================================================================


class TestEmitPromotionGateUnmet:
    def _run_set_state(self, ledger: Path, fp: str, new_state: str) -> int:
        import argparse
        args = argparse.Namespace(prefix=fp[:8], new_state=new_state, repo_root=None)
        # Override ledger_dir so it uses our tmp ledger
        return _promotion.cmd_improvements_set_state(args)

    def test_side_effect_escalation_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(a) gate-unmet transition writes a promotion-gate-unmet escalation record."""
        ledger = tmp_path / "improvements"
        fp = "a" * 64
        _seed_promotion_ticket(ledger, fp, all_gates=False)
        escalation_ledger = tmp_path / "esc-ledger"
        monkeypatch.setattr(_escalation, "ledger_dir", lambda r, c: escalation_ledger)
        monkeypatch.setattr(_improvement, "ledger_dir", lambda r, c: ledger)

        import argparse
        args = argparse.Namespace(prefix=fp[:8], new_state="promoted", repo_root=None)
        _promotion.cmd_improvements_set_state(args)

        files = _find_escalation_files(escalation_ledger)
        assert files, "promotion-gate-unmet escalation record must be written"
        record = json.loads(files[0].read_text())
        validate_escalation(record)
        assert record["problem_class"] == "promotion-gate-unmet"

    def test_control_flow_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(b) gate-unmet still returns 1 (error) as before."""
        ledger = tmp_path / "improvements"
        fp = "b" * 64
        _seed_promotion_ticket(ledger, fp, all_gates=False)
        monkeypatch.setattr(_improvement, "ledger_dir", lambda r, c: ledger)
        monkeypatch.setattr(_escalation, "ledger_dir", lambda r, c: tmp_path / "esc")

        import argparse
        args = argparse.Namespace(prefix=fp[:8], new_state="promoted", repo_root=None)
        rc = _promotion.cmd_improvements_set_state(args)
        assert rc == 1

    def test_non_gate_error_still_returns_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-gate PromotionError (illegal transition) still returns 1."""
        ledger = tmp_path / "improvements"
        fp = "c" * 64
        _seed_promotion_ticket(ledger, fp, all_gates=False)
        monkeypatch.setattr(_improvement, "ledger_dir", lambda r, c: ledger)

        import argparse
        # "candidate" → "promoted" is illegal FSM transition (not a gate error)
        ticket = json.loads((ledger / f"{fp}.json").read_text())
        ticket["state"] = "candidate"
        (ledger / f"{fp}.json").write_text(json.dumps(ticket))
        args = argparse.Namespace(prefix=fp[:8], new_state="promoted", repo_root=None)
        rc = _promotion.cmd_improvements_set_state(args)
        assert rc == 1

    def test_red_isolation_emit_failure_does_not_change_return(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED: emit throws RuntimeError → gate-unmet still returns 1."""
        ledger = tmp_path / "improvements"
        fp = "d" * 64
        _seed_promotion_ticket(ledger, fp, all_gates=False)
        monkeypatch.setattr(_improvement, "ledger_dir", lambda r, c: ledger)
        monkeypatch.setattr(
            _escalation, "bump_or_create",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("emit-fail"))
        )

        import argparse
        args = argparse.Namespace(prefix=fp[:8], new_state="promoted", repo_root=None)
        rc = _promotion.cmd_improvements_set_state(args)
        assert rc == 1

    def test_successful_transition_still_works(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All-gates-met ticket can still be promoted (no regressions)."""
        ledger = tmp_path / "improvements"
        fp = "e" * 64
        _seed_promotion_ticket(ledger, fp, all_gates=True)
        monkeypatch.setattr(_improvement, "ledger_dir", lambda r, c: ledger)

        import argparse
        args = argparse.Namespace(prefix=fp[:8], new_state="promoted", repo_root=None)
        rc = _promotion.cmd_improvements_set_state(args)
        assert rc == 0


# ===========================================================================
# Emit point (c): contract-schema-gap — orchestrator.cmd_phase_end
# ===========================================================================


class TestEmitContractSchemaGap:
    def test_side_effect_escalation_written(
        self, in_tmp_cwd: Path, sample_spec: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(a) failed evidence gate writes a contract-schema-gap escalation record."""
        escalation_ledger = in_tmp_cwd / "esc-ledger"
        monkeypatch.setattr(_escalation, "ledger_dir", lambda r, c: escalation_ledger)
        # Make gate_phase_end return failure tuple (evidence chain incomplete)
        monkeypatch.setattr(
            _escalation_emit._escalation if hasattr(_escalation_emit, "_escalation") else _escalation,
            "ledger_dir",
            lambda r, c: escalation_ledger,
        )
        import _evidence
        monkeypatch.setattr(
            _evidence, "gate_phase_end",
            lambda contracts_dir: ("evidence_failed", "missing review.json for codex-reviewer")
        )

        orchestrator.main(["init", "--spec", str(sample_spec)])
        orchestrator.main(["phase-start", "--phase", "1", "--contracts", "1"])
        orchestrator.main([
            "phase-end", "--phase", "1", "--status", "success", "--commits", "sha1"
        ])

        files = _find_escalation_files(escalation_ledger)
        assert files, "contract-schema-gap escalation record must be written"
        record = json.loads(files[0].read_text())
        validate_escalation(record)
        assert record["problem_class"] == "contract-schema-gap"

    def test_control_flow_returns_2(
        self, in_tmp_cwd: Path, sample_spec: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """(b) phase-end still returns 2 when evidence gate fails."""
        import _evidence
        monkeypatch.setattr(
            _evidence, "gate_phase_end",
            lambda contracts_dir: ("evidence_failed", "missing review.json for codex-reviewer")
        )
        monkeypatch.setattr(_escalation, "ledger_dir", lambda r, c: in_tmp_cwd / "esc")

        orchestrator.main(["init", "--spec", str(sample_spec)])
        orchestrator.main(["phase-start", "--phase", "1", "--contracts", "1"])
        rc = orchestrator.main([
            "phase-end", "--phase", "1", "--status", "success", "--commits", "sha1"
        ])
        assert rc == 2

    def test_red_isolation_emit_failure_does_not_change_return(
        self, in_tmp_cwd: Path, sample_spec: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RED: bump_or_create throws RuntimeError → phase-end still returns 2."""
        import _evidence
        monkeypatch.setattr(
            _evidence, "gate_phase_end",
            lambda contracts_dir: ("evidence_failed", "missing review.json for codex-reviewer")
        )
        monkeypatch.setattr(
            _escalation, "bump_or_create",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("emit-fail"))
        )

        orchestrator.main(["init", "--spec", str(sample_spec)])
        orchestrator.main(["phase-start", "--phase", "1", "--contracts", "1"])
        rc = orchestrator.main([
            "phase-end", "--phase", "1", "--status", "success", "--commits", "sha1"
        ])
        assert rc == 2
