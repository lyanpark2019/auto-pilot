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
