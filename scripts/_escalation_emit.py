"""Best-effort wrapper: emit a tier-1 give-up event to the escalation ledger.

Never raises — any I/O failure is logged and swallowed so the give-up code path
is unaffected.  Construction and import errors surface immediately (outside the
try) so programming bugs are visible in tests.  ``now`` is a required parameter;
no wall-clock calls here.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from _log import event


def emit_escalation(
    *,
    problem_class: str,
    suggested_enrich_query: str,
    approach: str,
    outcome: str,
    run_id: str,
    snippet: str,
    repo_root: Path,
    now: datetime,
) -> None:
    """Construct an Observation outside the try; swallow only I/O failures."""
    import _escalation  # noqa: PLC0415

    ledger = _escalation.ledger_dir(repo_root, None)
    obs = _escalation.Observation(
        problem_class=problem_class,
        suggested_enrich_query=suggested_enrich_query,
        approach=approach,
        outcome=outcome,
        run_id=run_id,
        snippet=snippet,
    )
    try:
        _escalation.bump_or_create(ledger, obs, repo_root=repo_root, now=now, dry_run=False)
    except Exception as exc:  # noqa: BLE001 — ledger I/O is best-effort; never perturb the give-up path
        event(
            "escalation.emit_failed",
            problem_class=problem_class,
            run_id=run_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
