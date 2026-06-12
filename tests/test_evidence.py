from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _contract  # noqa: E402
import _evidence  # noqa: E402

REVIEWERS = ("codex-reviewer", "claude-reviewer")


def _review(contract_id: str, verdict: str = "APPROVE") -> dict:
    return {
        "schema_version": 1,
        "reviewer": "codex-reviewer",
        "contract_id": contract_id,
        "verdict": verdict,
        "scope_check": "PASS",
        "findings": [],
        "verify_rerun": {"cmd": "pytest", "exit_code": 0},
        "reviewer_meta": {
            "model": "test",
            "started_at": "2026-06-10T00:00:00+00:00",
            "ended_at": "2026-06-10T00:00:01+00:00",
        },
    }


def _build_round(tmp_path: Path, *, contract_id: str = "iter-1/phase-1/contract-1/round-1",
                 verdict: str = "APPROVE", diff_text: bytes = b"diff --git a b\n",
                 drop: str = "") -> Path:
    """Materialize a contract round dir with a full (or partially broken) evidence chain.

    drop selects a defect: "" (none), "codex-ticket", "claude-review",
    "sha", "verdict", "contract-id", "empty-review", "bad-json-contract".
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
    for role in REVIEWERS:
        if drop == "codex-ticket" and role == "codex-reviewer":
            continue
        (cdir / "tickets" / f"{role}.json").write_text(json.dumps({"diff_sha256": sha}))
        out = cdir / "outputs" / role
        out.mkdir(parents=True)
        if drop == "claude-review" and role == "claude-reviewer":
            continue
        rid = contract_id if drop != "contract-id" else "iter-9/phase-9/contract-9/round-9"
        v = verdict if drop != "verdict" else "REJECT"
        (out / "review.json").write_text(json.dumps(_review(rid, v)))
        if drop == "empty-review" and role == "claude-reviewer":
            (out / "review.json").write_text("")
    return cdir


def test_full_chain_passes(tmp_path):
    cdir = _build_round(tmp_path)
    _evidence.assert_round_evidence(cdir)  # no raise


@pytest.mark.parametrize("drop", ["codex-ticket", "claude-review", "sha", "verdict",
                                  "contract-id", "empty-review", "bad-json-contract"])
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


# --- gate_phase_end unit tests ---

def test_gate_phase_end_no_contracts_tree(tmp_path):
    """Empty / missing contracts root → returns no_evidence_dirs tuple."""
    result = _evidence.gate_phase_end(tmp_path / "contracts")
    assert result is not None
    assert result[0] == "no_evidence_dirs"


def test_gate_phase_end_complete_chain(tmp_path):
    """Latest round with a valid complete chain → returns None (gate passes)."""
    root = tmp_path / "contracts"
    contract_dir = root / "iter-1" / "phase-1" / "contract-1"
    contract_dir.mkdir(parents=True)
    _build_round(contract_dir)  # creates contract_dir/round-1 with full chain
    result = _evidence.gate_phase_end(root)
    assert result is None


def test_gate_phase_end_broken_chain(tmp_path):
    """Latest round missing codex-ticket → returns evidence_failed tuple."""
    root = tmp_path / "contracts"
    contract_dir = root / "iter-1" / "phase-1" / "contract-1"
    contract_dir.mkdir(parents=True)
    _build_round(contract_dir, drop="codex-ticket")  # broken chain
    result = _evidence.gate_phase_end(root)
    assert result is not None
    assert result[0] == "evidence_failed"
