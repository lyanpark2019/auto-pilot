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
