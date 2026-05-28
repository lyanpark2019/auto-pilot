"""Tests for scripts/_dispatch.py and schemas/ticket.schema.json."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
TICKET_SCHEMA_PATH = ROOT / "schemas" / "ticket.schema.json"


def test_ticket_schema_is_valid_jsonschema():
    import jsonschema
    schema = json.loads(TICKET_SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)


import hashlib
import json as _json


def _make_contract_dir(tmp_path):
    import _contract
    contract = _json.loads((ROOT / "tests/fixtures/contracts/sample_contract.json").read_text())
    dest = tmp_path / "contracts" / "iter-1/phase-1/contract-1/round-1"
    dest.mkdir(parents=True)
    bundle = dest / "context-bundle"
    bundle.mkdir()
    (bundle / "spec.md").write_text("# spec\n")
    (bundle / "MANIFEST.txt").write_text(_contract._sha256(b"# spec\n") + "  spec.md\n")
    contract["context_bundle_path"] = str(bundle)
    # fixture sha alignment: contract claims must match bundle bytes
    contract["snapshot_shas"]["spec"] = _contract._sha256(b"# spec\n")
    contract["snapshot_shas"]["claude_md_chain"] = []
    _contract.write_contract(contract, dest / "contract.json")
    _contract.write_pm_signature(dest, run_id="run-test")
    return dest


def test_prepare_ticket_writes_signed_json(tmp_path):
    import _dispatch
    contract_dir = _make_contract_dir(tmp_path)
    worktree = tmp_path / "worktree"
    worktree.mkdir()

    ticket_path = _dispatch.prepare_subagent_ticket(
        contract_dir=contract_dir,
        worktree=worktree,
        subagent_role="worker",
    )
    assert ticket_path.exists()
    ticket = _json.loads(ticket_path.read_text())
    assert ticket["contract_id"] == "iter-1/phase-1/contract-1/round-1"
    assert ticket["subagent_role"] == "worker"
    assert ticket["output_dir"].endswith("/outputs/worker")
    # Self-consistent sha
    recomputed = _dispatch._compute_ticket_sha({k: v for k, v in ticket.items() if k != "ticket_sha"})
    assert ticket["ticket_sha"] == recomputed


def test_prepare_ticket_rejects_invalid_role(tmp_path):
    import _dispatch
    contract_dir = _make_contract_dir(tmp_path)
    with pytest.raises(ValueError):
        _dispatch.prepare_subagent_ticket(
            contract_dir=contract_dir,
            worktree=tmp_path / "wt",
            subagent_role="bogus-role",
        )


import subprocess


def test_freeze_diff_writes_diff_and_sha(tmp_path):
    import _dispatch
    # Create a real git worktree with one commit
    wt = tmp_path / "wt"
    wt.mkdir()
    subprocess.run(["git", "-C", str(wt), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(wt), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(wt), "config", "user.name", "t"], check=True)
    (wt / "a.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(wt), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "-m", "init"], check=True)
    base = subprocess.check_output(
        ["git", "-C", str(wt), "rev-parse", "HEAD"], text=True
    ).strip()
    (wt / "a.txt").write_text("hello\nworld\n")
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "-am", "edit"], check=True)

    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()

    diff_path = _dispatch.freeze_diff_for_review(wt, base, contract_dir)
    assert diff_path.exists()
    sha_path = diff_path.with_suffix(".diff.sha256")
    assert sha_path.exists()
    expected = _dispatch._contract._sha256(diff_path.read_bytes())
    assert sha_path.read_text().strip() == expected


REVIEW_SCHEMA_PATH = ROOT / "schemas" / "review.schema.json"


def test_review_schema_is_valid_jsonschema():
    import jsonschema
    schema = _json.loads(REVIEW_SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)


import time


def _write_review(out_dir, verdict="APPROVE"):
    review = {
        "schema_version": 1,
        "reviewer": "auto-pilot-codex-reviewer",
        "contract_id": "iter-1/phase-1/contract-1/round-1",
        "verdict": verdict,
        "scope_check": "PASS",
        "scope_drift_files": [],
        "scope_reduction_detected": False,
        "findings": [],
        "verify_rerun": {"cmd": "pytest -q", "exit_code": 0},
        "reviewer_meta": {"model": "gpt-5.5-high",
                          "started_at": "2026-05-28T10:00:00+00:00",
                          "ended_at":   "2026-05-28T10:01:00+00:00"}
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review.json").write_text(_json.dumps(review))
    (out_dir / "exit-code.txt").write_text("0\n")
    (out_dir / "done.marker").touch()


def test_collect_round_outcome_reads_all_outputs(tmp_path):
    import _dispatch
    contract_dir = tmp_path / "c"
    contract_dir.mkdir()
    _write_review(contract_dir / "outputs" / "worker", verdict="APPROVE")  # worker uses status, but for fixture reuse
    # Actually worker writes status.json not review.json; use proper shapes:
    worker_out = contract_dir / "outputs" / "worker"
    (worker_out).mkdir(parents=True, exist_ok=True)
    (worker_out / "status.json").write_text(_json.dumps({"status": "DONE", "diff_loc": 12}))
    (worker_out / "exit-code.txt").write_text("0\n")
    (worker_out / "done.marker").touch()
    _write_review(contract_dir / "outputs" / "codex-reviewer", verdict="APPROVE")
    _write_review(contract_dir / "outputs" / "claude-reviewer", verdict="REJECT")

    outcome = _dispatch.collect_round_outcome(contract_dir, timeout_per_agent_sec=2)
    assert outcome.worker_exit_code == 0
    assert outcome.codex_verdict == "APPROVE"
    assert outcome.claude_verdict == "REJECT"


def test_collect_round_outcome_times_out_if_done_marker_missing(tmp_path):
    import _dispatch
    contract_dir = tmp_path / "c"
    contract_dir.mkdir()
    (contract_dir / "outputs" / "worker").mkdir(parents=True)
    # No done.marker
    with pytest.raises(_dispatch.RoundCollectTimeout):
        _dispatch.collect_round_outcome(contract_dir, timeout_per_agent_sec=1)


def test_read_review_rejects_malformed(tmp_path):
    import _dispatch
    bad = tmp_path / "review.json"
    bad.write_text(_json.dumps({"schema_version": 1}))  # missing many required
    with pytest.raises(_dispatch.MalformedReviewError):
        _dispatch.read_review(bad)
