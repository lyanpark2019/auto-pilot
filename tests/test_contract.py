"""Tests for scripts/_contract.py and schemas/contract.schema.json."""
from __future__ import annotations
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "schemas" / "contract.schema.json"


def test_contract_schema_is_valid_jsonschema():
    """The contract schema file itself must be a valid JSON Schema draft 2020-12."""
    import jsonschema
    schema = json.loads(SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)


FIXTURE = ROOT / "tests" / "fixtures" / "contracts" / "sample_contract.json"


def test_sample_fixture_validates_against_schema():
    import jsonschema
    schema = json.loads(SCHEMA_PATH.read_text())
    data = json.loads(FIXTURE.read_text())
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(data)


import sys
sys.path.insert(0, str(ROOT / "scripts"))


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


import multiprocessing
import time


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
    import _contract
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
    assert (bundle / "CLAUDE.md").exists()
    assert (bundle / "MANIFEST.txt").exists()
    assert len(shas.spec) == 64
    assert len(shas.claude_md_chain) == 1
    assert shas.claude_md_chain[0] == _sha256_of((bundle / "CLAUDE.md").read_bytes())


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
