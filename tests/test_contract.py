"""Tests for scripts/_contract.py and schemas/contract.schema.json."""
from __future__ import annotations

import json
import multiprocessing
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "schemas" / "contract.schema.json"
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURE = ROOT / "tests" / "fixtures" / "contracts" / "sample_contract.json"


def test_contract_schema_is_valid_jsonschema():
    """The contract schema file itself must be a valid JSON Schema draft 2020-12."""
    import jsonschema
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)


def test_sample_fixture_validates_against_schema():
    import jsonschema
    schema = json.loads(SCHEMA_PATH.read_text())
    data = json.loads(FIXTURE.read_text())
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(data)


def test_validate_accepts_sample_fixture():
    import _contract
    data = json.loads(FIXTURE.read_text())
    _contract.validate(data)  # raises ContractValidationError on failure


def test_validate_rejects_missing_required_field():
    import _contract
    data = json.loads(FIXTURE.read_text())
    del data["title"]
    with pytest.raises(_contract.ContractValidationError):
        _contract.validate(data)


def test_validate_rejects_extra_unknown_field():
    import _contract
    data = json.loads(FIXTURE.read_text())
    data["unknown_key"] = "x"
    with pytest.raises(_contract.ContractValidationError):
        _contract.validate(data)


def test_write_then_read_roundtrip(tmp_path):
    import _contract
    data = json.loads(FIXTURE.read_text())
    target = tmp_path / "contract.json"
    _contract.write_contract(data, target)
    reloaded = _contract.read_contract(target)
    assert reloaded == data


def _writer_proc(path_str: str, sleep_sec: float, payload: dict) -> None:
    import sys
    sys.path.insert(0, str(Path(path_str).parent.parent.parent.parent / "scripts"))
    import _contract
    target = Path(path_str)
    with _contract.write_lock(target.parent):
        time.sleep(sleep_sec)
        _contract.write_contract(payload, target)


def test_write_lock_serializes_writers(tmp_path):
    """Two concurrent write_lock holders must serialize (one waits)."""
    target = tmp_path / "contract.json"
    data = json.loads(FIXTURE.read_text())

    p1 = multiprocessing.Process(target=_writer_proc, args=(str(target), 0.5, data))
    p2 = multiprocessing.Process(target=_writer_proc, args=(str(target), 0.0, data))
    t0 = time.time()
    p1.start()
    time.sleep(0.05)
    p2.start()
    p1.join()
    p2.join()
    elapsed = time.time() - t0
    assert elapsed >= 0.5, f"writers ran concurrently (elapsed={elapsed:.2f}s)"
    assert p1.exitcode == 0 and p2.exitcode == 0


def test_snapshot_context_copies_files_and_returns_shas(tmp_path):
    import _contract
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\nphase 1: do thing\n")
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# rules\nfile ≤500 lines\n")
    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)

    shas = _contract.snapshot_context(dest_dir, spec, [claude_md])

    bundle = dest_dir / "context-bundle"
    assert (bundle / "spec.md").exists()
    root_copy = bundle / "CLAUDE-chain-00-root.md"
    assert root_copy.exists()
    assert (bundle / "MANIFEST.txt").exists()
    assert len(shas.spec) == 64
    assert len(shas.claude_md_chain) == 1
    assert shas.claude_md_chain[0] == _sha256_of(root_copy.read_bytes())


def _sha256_of(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def test_verify_snapshots_detects_tamper(tmp_path):
    import _contract
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)
    shas = _contract.snapshot_context(dest_dir, spec, [])
    contract = json.loads(FIXTURE.read_text())
    contract["snapshot_shas"]["spec"] = shas.spec
    contract["snapshot_shas"]["claude_md_chain"] = shas.claude_md_chain
    contract["context_bundle_path"] = str(dest_dir / "context-bundle")
    _contract.write_contract(contract, dest_dir / "contract.json")

    # Clean: should pass
    _contract.verify_snapshots(dest_dir)
    # Tamper:
    (dest_dir / "context-bundle" / "spec.md").write_text("TAMPERED")
    with pytest.raises(_contract.SnapshotMismatchError):
        _contract.verify_snapshots(dest_dir)


def test_pm_signature_roundtrip(tmp_path):
    import _contract
    contract = json.loads(FIXTURE.read_text())
    dest_dir = tmp_path / "contract"
    dest_dir.mkdir()
    bundle = dest_dir / "context-bundle"
    bundle.mkdir()
    (bundle / "spec.md").write_text("# spec\n")
    (bundle / "MANIFEST.txt").write_text(_contract._sha256(b"# spec\n") + "  spec.md\n")
    _contract.write_contract(contract, dest_dir / "contract.json")

    _contract.write_pm_signature(dest_dir, run_id="run-abc123")
    _contract.verify_pm_signature(dest_dir)  # raises on mismatch


def test_pm_signature_detects_manifest_tamper(tmp_path):
    import _contract
    contract = json.loads(FIXTURE.read_text())
    dest_dir = tmp_path / "contract"
    dest_dir.mkdir()
    bundle = dest_dir / "context-bundle"
    bundle.mkdir()
    (bundle / "spec.md").write_text("# spec\n")
    (bundle / "MANIFEST.txt").write_text("original\n")
    _contract.write_contract(contract, dest_dir / "contract.json")
    _contract.write_pm_signature(dest_dir, run_id="run-abc123")

    (bundle / "MANIFEST.txt").write_text("TAMPERED\n")
    with pytest.raises(_contract.PMSignatureMismatchError):
        _contract.verify_pm_signature(dest_dir)


def test_is_killed_returns_true_after_canceled_touch(tmp_path):
    import _contract
    assert _contract.is_killed(tmp_path) is False
    (tmp_path / "CANCELED").touch()
    assert _contract.is_killed(tmp_path) is True


def _bind_snapshot_to_contract(dest_dir, shas) -> None:
    import _contract
    contract = json.loads(FIXTURE.read_text())
    contract["snapshot_shas"]["spec"] = shas.spec
    contract["snapshot_shas"]["claude_md_chain"] = shas.claude_md_chain
    contract["context_bundle_path"] = str(dest_dir / "context-bundle")
    _contract.write_contract(contract, dest_dir / "contract.json")


def test_verify_snapshots_roundtrips_non_alphabetical_chain(tmp_path):
    """A1 ORDER: chain order must survive re-derivation even when parent dir
    names are not in alphabetical order ([root, zebra, alpha])."""
    import _contract
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    root = tmp_path / "CLAUDE.md"
    root.write_text("ROOT\n")
    zdir = tmp_path / "zebra"
    zdir.mkdir()
    zc = zdir / "CLAUDE.md"
    zc.write_text("ZEBRA\n")
    adir = tmp_path / "alpha"
    adir.mkdir()
    ac = adir / "CLAUDE.md"
    ac.write_text("ALPHA\n")
    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)

    shas = _contract.snapshot_context(dest_dir, spec, [root, zc, ac])
    _bind_snapshot_to_contract(dest_dir, shas)

    # Clean bundle must round-trip — no false SnapshotMismatchError.
    _contract.verify_snapshots(dest_dir)
    assert len(shas.claude_md_chain) == 3


def test_snapshot_context_no_collision_on_same_leaf_dirs(tmp_path):
    """A1 COLLISION: two CLAUDE.md under same-named leaf dirs (src/api, lib/api)
    must produce distinct bundle copies — no silent overwrite/data loss."""
    import _contract
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    root = tmp_path / "CLAUDE.md"
    root.write_text("ROOT\n")
    sa = tmp_path / "src" / "api"
    sa.mkdir(parents=True)
    sac = sa / "CLAUDE.md"
    sac.write_text("SRC-API\n")
    la = tmp_path / "lib" / "api"
    la.mkdir(parents=True)
    lac = la / "CLAUDE.md"
    lac.write_text("LIB-API\n")
    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)

    shas = _contract.snapshot_context(dest_dir, spec, [root, sac, lac])
    _bind_snapshot_to_contract(dest_dir, shas)

    bundle = dest_dir / "context-bundle"
    chain_files = _contract._bundle_claude_files(bundle)
    # All three entries survive distinct on disk.
    assert len(chain_files) == 3
    assert len(shas.claude_md_chain) == 3
    contents = sorted(p.read_text() for p in chain_files)
    assert contents == ["LIB-API\n", "ROOT\n", "SRC-API\n"]
    # Clean round-trip in chain order.
    _contract.verify_snapshots(dest_dir)


def test_verify_claude_chain_detects_tamper(tmp_path):
    """FIX 4 (A1 bug-history area): _verify_claude_chain must raise
    SnapshotMismatchError when a bundle CLAUDE-chain-NN-*.md file is mutated
    after the snapshot was taken (tamper path previously unasserted)."""
    import _contract
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    root = tmp_path / "CLAUDE.md"
    root.write_text("ROOT\n")
    zdir = tmp_path / "z"
    zdir.mkdir()
    zc = zdir / "CLAUDE.md"
    zc.write_text("CHILD\n")
    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)

    # Build snapshot with a 2-entry chain.
    shas = _contract.snapshot_context(dest_dir, spec, [root, zc])
    _bind_snapshot_to_contract(dest_dir, shas)
    assert len(shas.claude_md_chain) == 2

    # Clean state must round-trip.
    _contract.verify_snapshots(dest_dir)

    # Tamper one of the CLAUDE-chain bundle files — any one in the chain.
    bundle = dest_dir / "context-bundle"
    chain_files = list(bundle.glob("CLAUDE-chain-*.md"))
    assert chain_files, "bundle must contain at least one chain file"
    chain_files[0].write_text("TAMPERED BY TEST\n")

    # _verify_claude_chain must detect the tampering and raise.
    with pytest.raises(_contract.SnapshotMismatchError):
        _contract.verify_snapshots(dest_dir)


def test_atomic_write_text_cleans_temp_on_keyboard_interrupt(tmp_path, monkeypatch):
    """A12: a BaseException (KeyboardInterrupt) mid-write must not leak the
    hidden temp file, and any pre-existing target must stay intact."""
    import _contract
    target = tmp_path / "contract.json"
    target.write_text("ORIGINAL\n")

    def boom(_fd: int) -> None:
        raise KeyboardInterrupt("mid-write")

    monkeypatch.setattr(_contract, "_fsync_file", boom)
    with pytest.raises(KeyboardInterrupt):
        _contract.atomic_write_text(target, "NEW")

    orphans = [p.name for p in tmp_path.iterdir() if p.name.startswith(".contract.json.")]
    assert orphans == [], f"leaked temp file(s): {orphans}"
    assert target.read_text() == "ORIGINAL\n"
