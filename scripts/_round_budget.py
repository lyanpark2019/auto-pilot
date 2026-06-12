"""Pure helpers for the orchestrator round-budget gate (extracted for size).

orchestrator.py sits at the 500-line module budget; these two pure functions
moved here when the review-status subcommand was added (2026-06-12).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _log import event


def load_findings(score_dir: Path, r: int) -> dict[str, Any]:
    """Load a findings-round-N.json file; return {} and log if missing."""
    p = score_dir / f"findings-round-{r}.json"
    if not p.exists():
        event("round_budget.missing_file", path=str(p))
        return {}
    parsed: dict[str, Any] = json.loads(p.read_text())
    return parsed


def count_findings(data: dict[str, Any]) -> int:
    """Sum reviewer finding counts from a findings file payload."""
    reviewers: dict[str, Any] = data.get("reviewers", {})
    return sum(int(v.get("count", 0)) for v in reviewers.values())
