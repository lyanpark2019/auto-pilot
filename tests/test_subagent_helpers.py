"""Tests for scripts/_subagent_helpers.py."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def test_read_ticket_validates_sha(tmp_path):
    import _dispatch
    import _subagent_helpers as h

    contract = json.loads((ROOT / "tests/fixtures/contracts/sample_contract.json").read_text())
    contract_dir = tmp_path / "c"
    contract_dir.mkdir()
    bundle = contract_dir / "context-bundle"
    bundle.mkdir()
    (bundle / "spec.md").write_text("# spec\n")
    (bundle / "MANIFEST.txt").write_text("x\n")
    contract["context_bundle_path"] = str(bundle)
    import _contract
    # fixture sha alignment: contract claims must match bundle bytes
    contract["snapshot_shas"]["spec"] = _contract._sha256(b"# spec\n")
    contract["snapshot_shas"]["claude_md_chain"] = []
    _contract.write_contract(contract, contract_dir / "contract.json")
    _contract.write_pm_signature(contract_dir, run_id="run-test")

    ticket_path = _dispatch.prepare_subagent_ticket(
        contract_dir=contract_dir,
        worktree=tmp_path / "wt",
        subagent_role="worker",
    )
    # Good read
    t = h.read_ticket(ticket_path)
    assert t["subagent_role"] == "worker"

    # Tamper ticket → ticket_sha mismatch
    bad = json.loads(ticket_path.read_text())
    bad["subagent_role"] = "claude-reviewer"
    ticket_path.write_text(json.dumps(bad))
    with pytest.raises(h.TicketShaMismatchError):
        h.read_ticket(ticket_path)


def test_assert_not_canceled_exits_99(tmp_path):
    import _subagent_helpers as h
    h.assert_not_canceled(tmp_path)  # no-op
    (tmp_path / "CANCELED").touch()
    with pytest.raises(SystemExit) as e:
        h.assert_not_canceled(tmp_path)
    assert e.value.code == 99


def test_compute_finding_hash_is_deterministic():
    import _subagent_helpers as h
    h1 = h.compute_finding_hash("src/x.py", 42, "Missing null check in parser")
    h2 = h.compute_finding_hash("src/x.py", 42, "  missing NULL check IN parser  ")
    # Same canonical form → same hash
    assert h1 == h2
    h3 = h.compute_finding_hash("src/x.py", 43, "Missing null check in parser")
    assert h3 != h1
