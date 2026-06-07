#!/usr/bin/env python3
"""Unified state file for vault-builder runs.

Stored at <vault>/meta/vault-builder-state.json. Replaces:
- notebooklm-vault-builder: meta/{score-state,score-content-state,ticket-state}.json
- autonomous-docs-loop: ~/.claude/state/<project>-docs.json
- sportic365 kb-update: build/kb-state.json

Old files remain readable via legacy_loaders; new runs write unified format.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def state_path(vault: Path) -> Path:
    return vault.expanduser().resolve() / "meta" / "vault-builder-state.json"


def load(vault: Path) -> dict[str, Any]:
    p = state_path(vault)
    if p.exists():
        return json.loads(p.read_text())
    return {
        "schema_version": 1,
        "vault": str(vault.expanduser().resolve()),
        "source_adapter": None,
        "round": 0,
        "scores": {"structural": None, "content": None},
        "tickets": {},
        "audits": [],
        "created_at": time.time(),
        "updated_at": time.time(),
    }


def save(vault: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = time.time()
    p = state_path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def migrate_legacy(vault: Path) -> dict[str, Any]:
    """If legacy nbm state files exist, fold them into unified state."""
    vault = vault.expanduser().resolve()
    meta = vault / "meta"
    state = load(vault)
    for legacy, key in [
        ("score-state.json", "structural"),
        ("score-content-state.json", "content"),
    ]:
        lf = meta / legacy
        if lf.exists():
            try:
                state["scores"][key] = json.loads(lf.read_text())
            except json.JSONDecodeError as exc:
                print(f"state: failed to migrate legacy {lf}: {type(exc).__name__}: {exc}", file=sys.stderr)
    ts = meta / "ticket-state.json"
    if ts.exists():
        try:
            legacy_tickets = json.loads(ts.read_text()).get("tickets", {})
            state.setdefault("tickets", {}).update(legacy_tickets)
        except json.JSONDecodeError as exc:
            print(f"state: failed to migrate legacy {ts}: {type(exc).__name__}: {exc}", file=sys.stderr)
    save(vault, state)
    return state
