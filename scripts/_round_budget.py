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
    """Load a findings-round-N.json file; return {} and log if missing/malformed.

    Returning {} routes to the orchestrator's documented exit 2 (missing file)
    rather than letting a JSONDecodeError/OSError escape and bypass the round-3
    hard-stop with an unhandled exit 1.
    """
    p = score_dir / f"findings-round-{r}.json"
    if not p.exists():
        event("round_budget.missing_file", path=str(p))
        return {}
    try:
        parsed = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        event("round_budget.unreadable_file", path=str(p), error=str(exc))
        return {}
    if not isinstance(parsed, dict):
        event("round_budget.non_object_file", path=str(p))
        return {}
    result: dict[str, Any] = parsed
    return result


def count_findings(data: dict[str, Any]) -> int:
    """Sum reviewer finding counts from a findings file payload.

    Non-dict reviewer entries (and a non-dict reviewers map) are skipped so a
    malformed payload yields a count, never an AttributeError.
    """
    reviewers = data.get("reviewers", {})
    if not isinstance(reviewers, dict):
        return 0
    return sum(
        int(v.get("count", 0))
        for v in reviewers.values()
        if isinstance(v, dict)
    )
