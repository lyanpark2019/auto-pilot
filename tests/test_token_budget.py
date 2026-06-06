"""Tests for the optional `token_budget` contract field (schemas/contract.schema.json).

Schema tests live here (not test_hooks.py / test_contract.py — owned elsewhere).
Validation goes through the existing helper: scripts/_contract.py::validate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "schemas" / "contract.schema.json"
FIXTURE = ROOT / "tests" / "fixtures" / "contracts" / "sample_contract.json"
sys.path.insert(0, str(ROOT / "scripts"))

import _contract  # noqa: E402


def _sample() -> dict[str, object]:
    data: dict[str, object] = json.loads(FIXTURE.read_text())
    return data


def test_contract_without_token_budget_still_validates() -> None:
    """token_budget is optional — pre-existing contracts stay valid (no version bump)."""
    data = _sample()
    assert "token_budget" not in data
    _contract.validate(data)


def test_contract_with_token_budget_validates() -> None:
    data = _sample()
    data["token_budget"] = 50_000
    _contract.validate(data)


def test_token_budget_minimum_boundary_accepted() -> None:
    data = _sample()
    data["token_budget"] = 1000
    _contract.validate(data)


def test_token_budget_below_minimum_rejected() -> None:
    data = _sample()
    data["token_budget"] = 999
    with pytest.raises(_contract.ContractValidationError):
        _contract.validate(data)


def test_token_budget_wrong_type_string_rejected() -> None:
    data = _sample()
    data["token_budget"] = "50000"
    with pytest.raises(_contract.ContractValidationError):
        _contract.validate(data)


def test_token_budget_fractional_number_rejected() -> None:
    data = _sample()
    data["token_budget"] = 1500.5
    with pytest.raises(_contract.ContractValidationError):
        _contract.validate(data)


def test_token_budget_null_rejected() -> None:
    data = _sample()
    data["token_budget"] = None
    with pytest.raises(_contract.ContractValidationError):
        _contract.validate(data)


def test_schema_declares_token_budget_optional() -> None:
    """token_budget must be a declared property (additionalProperties is false)
    but must NOT be required, and schema_version must remain 2."""
    schema = json.loads(SCHEMA_PATH.read_text())
    assert "token_budget" in schema["properties"]
    assert "token_budget" not in schema["required"]
    assert schema["properties"]["token_budget"]["type"] == "integer"
    assert schema["properties"]["token_budget"]["minimum"] == 1000
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["maximum"] == 2
