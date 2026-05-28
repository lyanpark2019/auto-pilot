"""Helpers invoked by subagents (worker, reviewers) at boot + during execution.

These run *inside* the subagent's Claude Code session; PM does NOT call them.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import _dispatch


class TicketShaMismatchError(Exception):
    """Raised when ticket.ticket_sha does not match recomputed canonical sha."""


def read_ticket(ticket_path: Path) -> dict[str, Any]:
    """Read ticket JSON, validate against schema, verify ticket_sha integrity."""
    data = json.loads(ticket_path.read_text())
    recomputed = _dispatch._compute_ticket_sha({k: v for k, v in data.items() if k != "ticket_sha"})
    if data.get("ticket_sha") != recomputed:
        raise TicketShaMismatchError(
            f"ticket_sha mismatch: {data.get('ticket_sha')!r} != {recomputed!r}"
        )
    _dispatch._validator().validate(data)
    return data


def assert_not_canceled(contract_dir: Path) -> None:
    """Exit 99 if PM has touched <contract_dir>/CANCELED. Cheap to poll."""
    if (contract_dir / "CANCELED").exists():
        sys.exit(99)


def compute_finding_hash(file: str, line: int | None, issue: str) -> str:
    """Standardized finding hash: sha256(file:line:canonical_issue).

    canonical_issue = first 8 lowercased whitespace-separated tokens.
    Same logical finding from any reviewer → same hash → pivot-detector
    counts correctly.
    """
    canonical = " ".join(issue.lower().strip().split()[:8])
    payload = f"{file}:{line if line is not None else '?'}:{canonical}"
    return hashlib.sha256(payload.encode()).hexdigest()
