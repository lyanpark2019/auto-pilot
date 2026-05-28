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
