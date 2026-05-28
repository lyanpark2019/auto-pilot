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
