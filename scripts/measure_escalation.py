"""Escalation-ledger measurement instrument — inc3 Phase 3.

Measures escalation state distribution, problem-class histogram, resolution
and recovery rates, and enrichment-pages-written over the escalation ledger.

Pure, deterministic, and order-independent — no datetime.now() or random.
Results are byte-stable: sub-dicts are sorted and ``json.dumps`` with
``sort_keys=True`` is idempotent across shuffled inputs.

CLI (via orchestrator.py):
    orchestrator.py measure-escalation [--repo-root <dir>] [--json]
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _escalation import _load_record, ledger_dir

_STATE_KEYS = ("abandoned", "enriched", "open", "resolved")
_PROBLEM_CLASS_KEYS = (
    "contract-schema-gap",
    "doom-loop",
    "enrich-gate-reject",
    "other",
    "promotion-gate-unmet",
    "unknown-library",
    "unresolved-error",
)


def measure(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure escalation-ledger metrics over a list of validated record dicts.

    Pure, deterministic, and order-independent.  Shuffling the input list
    produces an identical result dict.

    Returns a JSON-able dict with the following keys (all always present):

    ``total``
        Total number of records.
    ``by_state``
        Count per state (all 4 keys always: open/enriched/resolved/abandoned).
    ``by_problem_class``
        Count per problem_class (all 7 canonical keys always present; unknown
        values from records are silently ignored — canonical fixed keys intact).
    ``resolved``
        == by_state["resolved"]
    ``abandoned``
        == by_state["abandoned"]
    ``pending``
        by_state["open"] + by_state["enriched"]
    ``resolution_rate_pct``
        resolved / (resolved + abandoned) * 100, 1 decimal; 0.0 when denom == 0.
    ``recovery_rate_pct``
        resolved / total * 100, 1 decimal; 0.0 when total == 0.
    ``enrich_attempted``
        Count of records where record.get("enrichment") is a dict.
    ``enrichment_pages_written``
        Sum of enrichment.counts.written across records where enrichment is present.
    """
    by_state: dict[str, int] = {k: 0 for k in _STATE_KEYS}
    by_problem_class: dict[str, int] = {k: 0 for k in _PROBLEM_CLASS_KEYS}
    enrich_attempted = 0
    enrichment_pages_written = 0

    for record in records:
        state = record.get("state", "")
        if state in by_state:
            by_state[state] += 1

        problem_class = record.get("problem_class", "")
        if problem_class in by_problem_class:
            by_problem_class[problem_class] += 1

        enrichment = record.get("enrichment")
        if isinstance(enrichment, dict):
            enrich_attempted += 1
            counts = enrichment.get("counts")
            if isinstance(counts, dict):
                enrichment_pages_written += int(counts.get("written", 0))

    total = len(records)
    resolved = by_state["resolved"]
    abandoned = by_state["abandoned"]
    pending = by_state["open"] + by_state["enriched"]

    resolution_denom = resolved + abandoned
    resolution_rate_pct = (
        0.0 if resolution_denom == 0 else round(resolved / resolution_denom * 100, 1)
    )
    recovery_rate_pct = (
        0.0 if total == 0 else round(resolved / total * 100, 1)
    )

    return {
        "abandoned": abandoned,
        "by_problem_class": dict(sorted(by_problem_class.items())),
        "by_state": dict(sorted(by_state.items())),
        "enrich_attempted": enrich_attempted,
        "enrichment_pages_written": enrichment_pages_written,
        "pending": pending,
        "recovery_rate_pct": recovery_rate_pct,
        "resolution_rate_pct": resolution_rate_pct,
        "resolved": resolved,
        "total": total,
    }


def _load_records(repo_root: Path) -> list[dict[str, Any]]:
    """Load all valid escalation records from the home ledger for repo_root."""
    led = ledger_dir(repo_root, None)
    if not led.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(led.glob("*.json")):
        rec = _load_record(path)
        if rec is not None:
            out.append(rec)
    return out


def register_cli_subparsers(sub: Any) -> None:
    """Register ``measure-escalation`` onto the orchestrator CLI parser."""
    p = sub.add_parser("measure-escalation")
    p.add_argument(
        "--repo-root",
        default=".",
        dest="repo_root",
        help="project root (default: .); used to resolve the escalation ledger",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="output JSON (always true; flag kept for parity with siblings)",
    )
    p.set_defaults(func=cmd_measure_escalation)


def cmd_measure_escalation(args: Any) -> int:
    """CLI handler: print JSON escalation-ledger metrics.

    Missing ledger → empty record list → all-zeros result, rc 0.
    """
    repo_root = Path(getattr(args, "repo_root", ".")).resolve()
    records = _load_records(repo_root)
    result = measure(records)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
