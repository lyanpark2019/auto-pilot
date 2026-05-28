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


def test_atomic_write_output_and_mark_done_ordering(tmp_path):
    import _subagent_helpers as h
    out = tmp_path / "outputs" / "worker"
    out.mkdir(parents=True)

    h.atomic_write_output(out, "status.json", {"status": "DONE", "files_changed": ["a.py"]})
    h.write_exit_code(out, 0)
    h.mark_done(out)

    # All three artifacts present
    assert (out / "status.json").exists()
    assert (out / "exit-code.txt").exists()
    assert (out / "done.marker").exists()
    # done.marker mtime >= exit-code.txt mtime >= status.json mtime
    s_m = (out / "status.json").stat().st_mtime
    e_m = (out / "exit-code.txt").stat().st_mtime
    d_m = (out / "done.marker").stat().st_mtime
    assert d_m >= e_m >= s_m


def test_write_exit_code_atomic(tmp_path):
    import _subagent_helpers as h
    out = tmp_path / "outputs" / "worker"
    out.mkdir(parents=True)
    h.write_exit_code(out, 99)
    assert (out / "exit-code.txt").read_text().strip() == "99"
