"""PM-owned dispatch primitives for auto-pilot subagent ticket protocol."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

import _contract

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
TICKET_SCHEMA_PATH = SCHEMAS_DIR / "ticket.schema.json"
_VALID_ROLES = {"worker", "codex-reviewer", "claude-reviewer",
                "tdd-enforcer", "security-reviewer", "tech-critic-lead"}

_TICKET_VALIDATOR: jsonschema.Draft202012Validator | None = None


def _validator() -> jsonschema.Draft202012Validator:
    global _TICKET_VALIDATOR
    if _TICKET_VALIDATOR is None:
        schema = json.loads(TICKET_SCHEMA_PATH.read_text())
        _TICKET_VALIDATOR = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
    return _TICKET_VALIDATOR


def prepare_subagent_ticket(
    *,
    contract_dir: Path,
    worktree: Path,
    subagent_role: str,
    diff_path: Path | None = None,
) -> Path:
    """PM-side validation. Writes a signed ticket under <contract_dir>/tickets/<role>.json.

    Validates contract + PM-SIGNATURE + snapshots BEFORE writing the ticket.
    Returns the ticket path.

    Raises:
        ValueError on invalid role.
        ContractValidationError / SnapshotMismatchError / PMSignatureMismatchError
            on contract integrity failures.
    """
    if subagent_role not in _VALID_ROLES:
        raise ValueError(f"unknown subagent_role: {subagent_role!r}; allowed: {sorted(_VALID_ROLES)}")

    _contract.verify_pm_signature(contract_dir)
    _contract.verify_snapshots(contract_dir)
    contract = _contract.read_contract(contract_dir / "contract.json")

    output_dir = contract_dir / "outputs" / subagent_role
    output_dir.mkdir(parents=True, exist_ok=True)

    helper_abspath = str((Path(__file__).resolve().parent / "_subagent_helpers.py"))

    body: dict[str, Any] = {
        "schema_version":  1,
        "contract_id":     contract["id"],
        "base_sha":        contract["snapshot_shas"]["base_sha"],
        "contract_dir":    str(contract_dir.resolve()),
        "worktree":        str(worktree.resolve()),
        "subagent_role":   subagent_role,
        "output_dir":      str(output_dir.resolve()),
        "helper_abspath":  helper_abspath,
        "diff_path":       str(diff_path.resolve()) if diff_path else None,
        "diff_sha256":     None,
        "boot_ok_at":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if diff_path:
        body["diff_sha256"] = _contract._sha256(diff_path.read_bytes())
    body["ticket_sha"] = _compute_ticket_sha(body)

    _validator().validate(body)

    tickets_dir = contract_dir / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    ticket_path = tickets_dir / f"{subagent_role}.json"
    _contract._atomic_write_text(ticket_path, json.dumps(body, indent=2, sort_keys=True) + "\n")
    return ticket_path


def _compute_ticket_sha(body_without_sha: dict[str, Any]) -> str:
    """Deterministic sha256 of canonicalized ticket body sans the ticket_sha field."""
    canonical = json.dumps(body_without_sha, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
