from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _contract  # noqa: E402
import _evidence  # noqa: E402

REVIEWERS = ("codex-reviewer", "claude-reviewer")


def _review(contract_id: str, verdict: str = "APPROVE",
            abstain_reason: str | None = None,
            scope_check: str | None = None,
            reviewer: str = "codex-reviewer",
            rerun_exit_code: int = 0) -> dict:
    meta: dict[str, str] = {
        "model": "test",
        "started_at": "2026-06-10T00:00:00+00:00",
        "ended_at": "2026-06-10T00:00:01+00:00",
    }
    if abstain_reason is not None:
        meta["abstain_reason"] = abstain_reason
    resolved_scope_check = scope_check if scope_check is not None else (
        "SKIPPED" if verdict == "ABSTAIN" else "PASS"
    )
    return {
        "schema_version": 1,
        "reviewer": reviewer,
        "contract_id": contract_id,
        "verdict": verdict,
        "scope_check": resolved_scope_check,
        "findings": [],
        "verify_rerun": {"cmd": "pytest", "exit_code": rerun_exit_code},
        "reviewer_meta": meta,
    }


def _build_round(tmp_path: Path, *, contract_id: str = "iter-1/phase-1/contract-1/round-1",
                 diff_text: bytes = b"diff --git a b\n",
                 drop: str = "",
                 per_role_verdict: dict | None = None,
                 abstain_reason: str | None = None,
                 scope_check_override: dict | None = None,
                 reviewer_override: dict | None = None,
                 rerun_exit_code_override: dict | None = None) -> Path:
    """Materialize a contract round dir with a full (or partially broken) evidence chain.

    drop selects a defect: "" (none), "codex-ticket", "codex-review",
    "claude-review", "sha", "verdict", "contract-id", "empty-review",
    "bad-json-contract", "pm-signature", "signature-tamper".
    "codex-review": ticket IS written for codex-reviewer, but its review.json
    is skipped — mirrors "claude-review" which does the same for claude.
    per_role_verdict overrides verdict for specific roles: {"codex-reviewer": "ABSTAIN"}.
    abstain_reason is included in reviewer_meta when a role's verdict is ABSTAIN.
    scope_check_override overrides scope_check for specific roles: {"claude-reviewer": "SKIPPED"}.
    reviewer_override writes a wrong reviewer field: {"claude-reviewer": "codex-reviewer"}.
    rerun_exit_code_override sets verify_rerun.exit_code per role: {"claude-reviewer": 1}.
    """
    cdir = tmp_path / "round-1"
    (cdir / "review-input").mkdir(parents=True)
    (cdir / "tickets").mkdir()
    sha = _contract._sha256(diff_text)
    (cdir / "review-input" / "frozen.diff").write_bytes(diff_text)
    sha_to_write = sha if drop != "sha" else "0" * 64
    (cdir / "review-input" / "frozen.diff.sha256").write_text(sha_to_write + "\n")
    if drop == "bad-json-contract":
        (cdir / "contract.json").write_text("{ not json")
    else:
        (cdir / "contract.json").write_text(json.dumps({"id": contract_id}))
    if drop != "pm-signature":
        bundle = cdir / "context-bundle"
        bundle.mkdir()
        (bundle / "MANIFEST.txt").write_text("fixture manifest\n")
        _contract.write_pm_signature(cdir, run_id="test-run")
        if drop == "signature-tamper":
            sig_path = cdir / "PM-SIGNATURE"
            sig = json.loads(sig_path.read_text())
            sig["contract_sha"] = "0" * 64
            sig_path.write_text(json.dumps(sig) + "\n")
    for role in REVIEWERS:
        if drop == "codex-ticket" and role == "codex-reviewer":
            continue
        (cdir / "tickets" / f"{role}.json").write_text(json.dumps({"diff_sha256": sha}))
        out = cdir / "outputs" / role
        out.mkdir(parents=True)
        if drop == "claude-review" and role == "claude-reviewer":
            continue
        if drop == "codex-review" and role == "codex-reviewer":
            continue
        rid = contract_id if drop != "contract-id" else "iter-9/phase-9/contract-9/round-9"
        v = "REJECT" if drop == "verdict" else "APPROVE"
        if per_role_verdict and role in per_role_verdict:
            v = per_role_verdict[role]
        sc = (scope_check_override or {}).get(role)
        rv = (reviewer_override or {}).get(role, role)
        rerun_rc = (rerun_exit_code_override or {}).get(role, 0)
        (out / "review.json").write_text(
            json.dumps(_review(rid, v, abstain_reason if v == "ABSTAIN" else None,
                               scope_check=sc, reviewer=rv, rerun_exit_code=rerun_rc)))
        if drop == "empty-review" and role == "claude-reviewer":
            (out / "review.json").write_text("")
    return cdir


def test_full_chain_passes(tmp_path):
    cdir = _build_round(tmp_path)
    _evidence.assert_round_evidence(cdir)  # no raise


def test_missing_pm_signature_rejects(tmp_path):
    cdir = _build_round(tmp_path, drop="pm-signature")
    with pytest.raises(_evidence.EvidenceError, match="PM-SIGNATURE"):
        _evidence.assert_round_evidence(cdir)


def test_tampered_pm_signature_rejects(tmp_path):
    cdir = _build_round(tmp_path, drop="signature-tamper")
    with pytest.raises(_evidence.EvidenceError, match="PM-SIGNATURE"):
        _evidence.assert_round_evidence(cdir)


@pytest.mark.parametrize("drop", ["codex-ticket", "codex-review", "claude-review", "sha",
                                  "verdict", "contract-id", "empty-review",
                                  "bad-json-contract"])
def test_each_defect_rejects(tmp_path, drop):
    cdir = _build_round(tmp_path, drop=drop)
    with pytest.raises(_evidence.EvidenceError):
        _evidence.assert_round_evidence(cdir)


def test_latest_round_dirs_picks_max_phase_latest_round(tmp_path):
    root = tmp_path / "contracts"
    # phase-1 (older), phase-2 (current); phase-2/contract-1 has rounds 1 and 2
    for rel in [
        "iter-1/phase-1/contract-1/round-1",
        "iter-1/phase-2/contract-1/round-1",
        "iter-1/phase-2/contract-1/round-2",
        "iter-1/phase-2/contract-2/round-1",
    ]:
        (root / rel).mkdir(parents=True)
    dirs = _evidence.latest_round_dirs_for_active_phase(root)
    names = sorted(str(d.relative_to(root)) for d in dirs)
    assert names == [
        "iter-1/phase-2/contract-1/round-2",
        "iter-1/phase-2/contract-2/round-1",
    ]


def test_latest_round_dirs_empty_when_no_contracts(tmp_path):
    assert _evidence.latest_round_dirs_for_active_phase(tmp_path / "nope") == []


def test_latest_round_dirs_scopes_to_current_iteration(tmp_path):
    """C1 regression: a later iteration on a LOWER phase must not be masked by an
    earlier iteration that reached a higher phase."""
    root = tmp_path / "contracts"
    for rel in [
        "iter-1/phase-1/contract-1/round-1",
        "iter-1/phase-2/contract-1/round-1",   # iter-1 reached phase 2
        "iter-2/phase-1/contract-1/round-1",   # current iteration, phase 1
    ]:
        (root / rel).mkdir(parents=True)
    dirs = _evidence.latest_round_dirs_for_active_phase(root)
    names = sorted(str(d.relative_to(root)) for d in dirs)
    assert names == ["iter-2/phase-1/contract-1/round-1"], names


def test_latest_round_dirs_ignores_archive_iter_dirs(tmp_path):
    """A non-iter-prefixed dir (e.g. archive-step0-iter-9) must never be selected."""
    root = tmp_path / "contracts"
    for rel in [
        "iter-1/phase-1/contract-1/round-1",
        "archive-step0-iter-9/phase-9/contract-1/round-1",
    ]:
        (root / rel).mkdir(parents=True)
    dirs = _evidence.latest_round_dirs_for_active_phase(root)
    names = sorted(str(d.relative_to(root)) for d in dirs)
    assert names == ["iter-1/phase-1/contract-1/round-1"], names


# --- gate_phase_end unit tests ---

def test_gate_phase_end_no_contracts_tree(tmp_path):
    """Empty / missing contracts root → returns no_evidence_dirs tuple."""
    result = _evidence.gate_phase_end(tmp_path / "contracts")
    assert result is not None
    assert result[0] == "no_evidence_dirs"


def test_gate_phase_end_complete_chain(tmp_path):
    """Latest round with a valid complete chain → returns approved count (int ≥ 1)."""
    root = tmp_path / "contracts"
    contract_dir = root / "iter-1" / "phase-1" / "contract-1"
    contract_dir.mkdir(parents=True)
    _build_round(contract_dir)  # creates contract_dir/round-1 with full chain
    result = _evidence.gate_phase_end(root)
    assert isinstance(result, int), f"expected int, got {result!r}"
    assert result == 1


def test_gate_phase_end_broken_chain(tmp_path):
    """Latest round missing codex-ticket → returns evidence_failed tuple."""
    root = tmp_path / "contracts"
    contract_dir = root / "iter-1" / "phase-1" / "contract-1"
    contract_dir.mkdir(parents=True)
    _build_round(contract_dir, drop="codex-ticket")  # broken chain
    result = _evidence.gate_phase_end(root)
    assert result is not None
    assert result[0] == "evidence_failed"


def test_gate_phase_end_missing_pm_signature_blocks(tmp_path):
    root = tmp_path / "contracts"
    contract_dir = root / "iter-1" / "phase-1" / "contract-1"
    contract_dir.mkdir(parents=True)
    _build_round(contract_dir, drop="pm-signature")
    result = _evidence.gate_phase_end(root)
    assert result is not None
    assert result[0] == "evidence_failed"
    assert "PM-SIGNATURE" in result[1]


def test_codex_abstain_with_reason_passes(tmp_path):
    """§3a: honest codex timeout (ABSTAIN + abstain_reason) + claude APPROVE = valid round."""
    cdir = _build_round(tmp_path,
                        per_role_verdict={"codex-reviewer": "ABSTAIN"},
                        abstain_reason="codex-timeout")
    _evidence.assert_round_evidence(cdir)  # no raise


def test_codex_abstain_without_reason_blocks(tmp_path):
    cdir = _build_round(tmp_path, per_role_verdict={"codex-reviewer": "ABSTAIN"})
    with pytest.raises(_evidence.EvidenceError, match="abstain_reason"):
        _evidence.assert_round_evidence(cdir)


def test_claude_abstain_always_blocks(tmp_path):
    """The cold-Claude verdict is load-bearing — only codex may abstain."""
    cdir = _build_round(tmp_path,
                        per_role_verdict={"claude-reviewer": "ABSTAIN"},
                        abstain_reason="any-reason")
    with pytest.raises(_evidence.EvidenceError, match="claude-reviewer"):
        _evidence.assert_round_evidence(cdir)


def test_codex_abstain_with_claude_reject_blocks(tmp_path):
    cdir = _build_round(tmp_path,
                        per_role_verdict={"codex-reviewer": "ABSTAIN",
                                          "claude-reviewer": "REJECT"},
                        abstain_reason="codex-timeout")
    with pytest.raises(_evidence.EvidenceError, match="claude-reviewer"):
        _evidence.assert_round_evidence(cdir)


def test_codex_review_missing_still_blocks_in_abstain_era(tmp_path):
    """Run-3 hardening intact: MISSING codex review.json is never an implicit abstain."""
    cdir = _build_round(tmp_path, drop="codex-review")
    with pytest.raises(_evidence.EvidenceError, match="codex-reviewer: review.json missing"):
        _evidence.assert_round_evidence(cdir)


def test_codex_abstain_whitespace_only_reason_blocks(tmp_path):
    """Carry-in Task-3 review: whitespace-only abstain_reason is not a valid reason."""
    cdir = _build_round(tmp_path, per_role_verdict={"codex-reviewer": "ABSTAIN"},
                        abstain_reason="   ")
    with pytest.raises(_evidence.EvidenceError, match="abstain_reason"):
        _evidence.assert_round_evidence(cdir)


def test_approve_with_scope_check_skipped_is_blocked(tmp_path):
    """APPROVE + scope_check=SKIPPED is invalid — SKIPPED only allowed on ABSTAIN."""
    cdir = _build_round(tmp_path,
                        scope_check_override={"claude-reviewer": "SKIPPED"})
    with pytest.raises(_evidence.EvidenceError, match="SKIPPED"):
        _evidence.assert_round_evidence(cdir)


def test_abstain_with_scope_check_skipped_passes(tmp_path):
    """codex ABSTAIN+reason + scope_check=SKIPPED is the normal wrapper-emitted shape."""
    cdir = _build_round(tmp_path,
                        per_role_verdict={"codex-reviewer": "ABSTAIN"},
                        abstain_reason="codex-timeout")
    # scope_check is SKIPPED by default in _review when verdict==ABSTAIN
    _evidence.assert_round_evidence(cdir)  # no raise


# --- Task 1: reviewer field ↔ role dir cross-check ---

def test_reviewer_field_mismatch_blocks(tmp_path):
    """claude-reviewer dir holding reviewer=codex-reviewer must be rejected."""
    cdir = _build_round(tmp_path,
                        reviewer_override={"claude-reviewer": "codex-reviewer"})
    with pytest.raises(_evidence.EvidenceError,
                       match="claude-reviewer.*codex-reviewer.*role dir"):
        _evidence.assert_round_evidence(cdir)


def test_reviewer_field_match_passes(tmp_path):
    """Each role dir has matching reviewer field — no raise."""
    cdir = _build_round(tmp_path)
    _evidence.assert_round_evidence(cdir)  # no raise


# --- Task 2: APPROVE must carry scope_check=PASS ---

def test_approve_with_scope_check_fail_blocks(tmp_path):
    """APPROVE + scope_check=FAIL is contradictory evidence and must be rejected."""
    cdir = _build_round(tmp_path,
                        scope_check_override={"claude-reviewer": "FAIL"})
    with pytest.raises(_evidence.EvidenceError,
                       match="out-of-scope diff cannot be approved"):
        _evidence.assert_round_evidence(cdir)


def test_approve_with_scope_check_pass_passes(tmp_path):
    """APPROVE + scope_check=PASS (correct reviewer fields) must pass end-to-end."""
    cdir = _build_round(tmp_path)
    _evidence.assert_round_evidence(cdir)  # no raise


# --- E6: APPROVE must carry verify_rerun.exit_code == 0 ---

def test_approve_with_failing_verify_rerun_blocks(tmp_path):
    """APPROVE + verify_rerun.exit_code != 0 is contradictory evidence — blocked."""
    cdir = _build_round(tmp_path,
                        rerun_exit_code_override={"claude-reviewer": 1})
    with pytest.raises(_evidence.EvidenceError,
                       match="APPROVE with verify_rerun.exit_code"):
        _evidence.assert_round_evidence(cdir)


def test_approve_with_passing_verify_rerun_passes(tmp_path):
    """APPROVE + verify_rerun.exit_code == 0 (the default) must pass."""
    cdir = _build_round(tmp_path,
                        rerun_exit_code_override={"codex-reviewer": 0,
                                                  "claude-reviewer": 0})
    _evidence.assert_round_evidence(cdir)  # no raise


def test_codex_abstain_keeps_nonzero_rerun_exit_code(tmp_path):
    """A codex honest ABSTAIN carries verify_rerun.exit_code=124 (timeout) and is
    still valid — the exit_code==0 rule applies to APPROVE only."""
    cdir = _build_round(tmp_path,
                        per_role_verdict={"codex-reviewer": "ABSTAIN"},
                        abstain_reason="codex-timeout",
                        rerun_exit_code_override={"codex-reviewer": 124})
    _evidence.assert_round_evidence(cdir)  # no raise


# --- E11/E19: latest round picked numerically, not lexically ---

def test_latest_round_dirs_uses_numeric_round_sort(tmp_path):
    """round-10 must beat round-9 — lexical sort would wrongly pick round-9."""
    root = tmp_path / "contracts"
    for rel in [
        "iter-1/phase-1/contract-1/round-1",
        "iter-1/phase-1/contract-1/round-2",
        "iter-1/phase-1/contract-1/round-9",
        "iter-1/phase-1/contract-1/round-10",
    ]:
        (root / rel).mkdir(parents=True)
    dirs = _evidence.latest_round_dirs_for_active_phase(root)
    names = sorted(str(d.relative_to(root)) for d in dirs)
    assert names == ["iter-1/phase-1/contract-1/round-10"], names
