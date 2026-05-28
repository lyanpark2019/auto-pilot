"""Garbage-collection helpers for auto-pilot state dir.

Note: archive_terminal_contracts() is DEFERRED to the headless cost-cap
follow-up spec. Only ticket sweep + bundle-size enforcement ship in PR1.
"""
from __future__ import annotations

import os
import time
from pathlib import Path


class BundleTooLargeError(Exception):
    """Context-bundle exceeded size cap; PM must slice the contract."""


def reject_oversized_bundle(bundle_dir: Path, max_bytes: int = 200_000) -> None:
    """Sum bytes of all files under bundle_dir. Raise if exceeds max_bytes."""
    total = 0
    for f in bundle_dir.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    if total > max_bytes:
        raise BundleTooLargeError(
            f"bundle {bundle_dir} = {total} bytes exceeds cap {max_bytes}; "
            "tech-critic-lead must slice contract"
        )


def sweep_orphan_tickets(state_dir: Path, max_age_hours: int = 24) -> list[str]:
    """Remove tickets older than max_age_hours whose contract dir has no done.marker.

    Returns list of removed ticket paths (str).
    """
    cutoff = time.time() - max_age_hours * 3600
    removed: list[str] = []
    contracts_root = state_dir / "contracts"
    if not contracts_root.exists():
        return removed
    for ticket in contracts_root.rglob("tickets/*.json"):
        try:
            mtime = ticket.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime > cutoff:
            continue
        # role name from ticket filename
        role = ticket.stem
        outputs_done = ticket.parent.parent / "outputs" / role / "done.marker"
        if outputs_done.exists():
            continue  # legitimately completed; leave ticket for forensic
        ticket.unlink(missing_ok=True)
        removed.append(str(ticket))
    return removed
