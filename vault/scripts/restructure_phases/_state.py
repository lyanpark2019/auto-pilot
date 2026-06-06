"""State file IO. Idempotent + resume-safe."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def load(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return _seed()
    try:
        data = json.loads(state_path.read_text())
        if data.get("schema_version") != SCHEMA_VERSION:
            data["schema_version"] = SCHEMA_VERSION
        return data
    except json.JSONDecodeError:
        backup = state_path.with_suffix(f".corrupt-{int(time.time())}.json")
        state_path.rename(backup)
        return _seed()


def save(state_path: Path, data: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(state_path)


def _seed() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "current_phase": 0,
        "phases": {
            "1_backup": {"status": "pending"},
            "2_rename_simple": {"status": "pending"},
            "3_sportic365_merge": {"status": "pending"},
            "4_notebooklm_split": {"status": "pending"},
            "5_new_vault_skeletons": {"status": "pending"},
            "6_vault_build_per_domain": {"status": "pending", "domains": {}},
            "7_notebooklm_create": {"status": "pending", "notebooks_created": []},
            "8_cleanup": {"status": "pending"},
        },
        "watchdog": {"consecutive_no_delta_rounds": 0, "abort_threshold": 2},
        "errors": [],
    }


def mark_phase(state: dict, phase_name: str, status: str, **extra) -> None:
    p = state["phases"].setdefault(phase_name, {})
    p["status"] = status
    p["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for k, v in extra.items():
        p[k] = v


def append_error(state: dict, phase_name: str, error: str) -> None:
    state["errors"].append(
        {
            "phase": phase_name,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "msg": error,
        }
    )
