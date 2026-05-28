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
