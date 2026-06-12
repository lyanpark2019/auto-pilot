"""Producer/validator for dispatch ``contract-check.json`` artifacts."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import _contract

JsonObject = dict[str, Any]


class ContractCheckError(Exception):
    """Raised when a contract-check artifact is absent, stale, or invalid."""


def _as_str(value: object, name: str) -> str:
    if isinstance(value, str):
        return value
    raise ContractCheckError(f"{name} must be a string")


def signature_status(contract_dir: Path) -> JsonObject:
    """Return verified PM-SIGNATURE status for ``contract_dir``."""
    sig_path = contract_dir / "PM-SIGNATURE"
    try:
        _contract.verify_pm_signature(contract_dir)
        sig_bytes = sig_path.read_bytes()
        sig = json.loads(sig_bytes)
        contract_sha = _as_str(sig.get("contract_sha"), "PM-SIGNATURE contract_sha")
        manifest_sha = _as_str(sig.get("manifest_sha"), "PM-SIGNATURE manifest_sha")
    except (OSError, json.JSONDecodeError, KeyError, TypeError,
            _contract.PMSignatureMismatchError, ContractCheckError) as exc:
        raise ContractCheckError(f"PM-SIGNATURE invalid: {exc}") from exc
    return {
        "verified": True,
        "signature_sha256": _contract._sha256(sig_bytes),
        "contract_sha256": contract_sha,
        "manifest_sha256": manifest_sha,
    }


def build_artifact(contract_path: Path) -> JsonObject:
    """Build a pass artifact, failing unless PM-SIGNATURE verifies."""
    contract_bytes = contract_path.read_bytes()
    contract_sha = _contract._sha256(contract_bytes)
    sig = signature_status(contract_path.parent)
    if sig["contract_sha256"] != contract_sha:
        raise ContractCheckError("PM-SIGNATURE status contract sha does not match contract.json")
    return {
        "contract_sha256": contract_sha,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": json.loads(contract_bytes.decode()).get("schema_version", 1),
        "result": "pass",
        "pm_signature": sig,
    }


def _signature_artifact(artifact: JsonObject) -> JsonObject:
    value = artifact.get("pm_signature")
    if not isinstance(value, dict) or value.get("verified") is not True:
        raise ContractCheckError("PM-SIGNATURE status missing or not verified in contract-check artifact")
    return cast(JsonObject, value)


def assert_artifact_fresh(contract_dir: Path, artifact: JsonObject) -> None:
    """Raise unless artifact matches current contract bytes and PM-SIGNATURE bytes."""
    if artifact.get("result") != "pass":
        raise ContractCheckError(f"contract-check artifact result is not 'pass': {artifact.get('result')!r}")
    contract_path = contract_dir / "contract.json"
    actual_sha = _contract._sha256(contract_path.read_bytes())
    recorded_sha = artifact.get("contract_sha256", "")
    if actual_sha != recorded_sha:
        raise ContractCheckError(
            "contract file modified since last dispatch-contract-check "
            f"(expected={recorded_sha!r}, actual={actual_sha!r})"
        )
    recorded_sig = _signature_artifact(artifact)
    if recorded_sig.get("contract_sha256") != actual_sha:
        raise ContractCheckError("PM-SIGNATURE status contract sha does not match contract.json")
    current_sig = signature_status(contract_dir)
    if recorded_sig.get("signature_sha256") != current_sig["signature_sha256"]:
        raise ContractCheckError("PM-SIGNATURE modified since last dispatch-contract-check")
    if recorded_sig.get("manifest_sha256") != current_sig["manifest_sha256"]:
        raise ContractCheckError("PM-SIGNATURE manifest sha status mismatch")
