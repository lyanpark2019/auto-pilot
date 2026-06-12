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
    "sha", "verdict", "contract-id".
    """
    cdir = tmp_path / "round-1"
    (cdir / "review-input").mkdir(parents=True)
    (cdir / "tickets").mkdir()
    sha = _contract._sha256(diff_text)
    (cdir / "review-input" / "frozen.diff").write_bytes(diff_text)
    sha_to_write = sha if drop != "sha" else "0" * 64
    (cdir / "review-input" / "frozen.diff.sha256").write_text(sha_to_write + "\n")
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
    return cdir


def test_full_chain_passes(tmp_path):
    cdir = _build_round(tmp_path)
    _evidence.assert_round_evidence(cdir)  # no raise


@pytest.mark.parametrize("drop", ["codex-ticket", "claude-review", "sha", "verdict", "contract-id"])
def test_each_defect_rejects(tmp_path, drop):
    cdir = _build_round(tmp_path, drop=drop)
    with pytest.raises(_evidence.EvidenceError):
        _evidence.assert_round_evidence(cdir)
