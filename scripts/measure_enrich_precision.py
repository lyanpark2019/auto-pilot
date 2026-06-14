"""Gate-precision measurement instrument — inc2-enrich Phase 4a.

Measures admit/reject rates, per-tier breakdown, reason histogram,
evidence-complete rate, and advisory-judge disagreements over a batch
of enrichment-evidence candidate dicts.

Runs the real ``_enrich_gate.evaluate`` on each candidate.  Pure,
deterministic and order-independent — no datetime.now() or random.
Results are byte-stable: ``by_tier`` is sorted and ``json.dumps``
with ``sort_keys=True`` is idempotent across shuffled inputs.

CLI (via orchestrator.py):
    orchestrator.py measure-enrich --candidates <dir|file> [--json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from _enrich_gate import evaluate
from _enrich_persist import _load_candidates

_KNOWN_TIERS = ("official", "community")


def _reason_category(reason: str) -> str:
    """Collapse variable URL/literal detail so reasons aggregate across a batch.

    ``url='https://…'`` → ``url=<…>``; remaining ``'…'`` single-quoted
    literals → ``<…>``.  The structural prefix (e.g. "corroboration sha256
    mismatch (tamper) for") is preserved so histograms remain meaningful.
    """
    r = re.sub(r"url='[^']*'", "url=<…>", reason)
    r = re.sub(r"'[^']*'", "<…>", r)
    return r


def measure(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure gate-precision over a list of enrichment-evidence candidates.

    Pure, deterministic, and order-independent.  Shuffling the input
    list produces an identical result dict.

    Returns a JSON-able dict with the following keys (sorted):

    ``admitted``
        Count of candidates with verdict == 'admit'.
    ``admit_rate_pct``
        admitted / total * 100, 1 decimal; 0.0 when total == 0.
    ``advisory_judge_abstains``
        Count of candidates where advisory_judge.verdict == 'abstain'.
        Abstains are NOT counted as disagreements.
    ``advisory_judge_disagreements``
        Count of candidates where advisory_judge is a dict with a 'verdict'
        key of 'admit' or 'reject' that differs from the gate verdict.
        None-judge candidates and abstain verdicts are not counted.
    ``by_tier``
        {'official': {'admitted': int, 'rejected': int},
         'community': {'admitted': int, 'rejected': int}},
        sorted by key for byte-stable serialisation.
        Non-official/community tier values are bucketed under their literal key.
    ``evidence_complete_pct``
        % of candidates with evidence_complete is True, 1 decimal; 0.0 when
        total == 0.
    ``reason_histogram``
        Aggregated count of every reason string across all candidates, sorted
        by key.  Reasons are categorised (variable URLs/literals collapsed)
        via ``_reason_category`` so a batch with many distinct URLs aggregates
        into one bucket rather than N count-1 buckets.
    ``rejected``
        Count of candidates with verdict == 'reject'.
    ``total``
        Total number of candidates evaluated.
    """
    total = len(candidates)

    admitted = 0
    rejected = 0
    evidence_complete_count = 0
    advisory_disagreements = 0
    advisory_abstains = 0
    by_tier: dict[str, dict[str, int]] = {}
    reason_counts: dict[str, int] = {}

    for candidate in candidates:
        result = evaluate(candidate)
        verdict = result["verdict"]
        source_tier: str = result["source_tier"]
        ev_complete: bool = bool(result["evidence_complete"])
        reasons: list[str] = result.get("reasons") or []
        advisory_judge = result.get("advisory_judge")

        if verdict == "admit":
            admitted += 1
        else:
            rejected += 1

        if ev_complete:
            evidence_complete_count += 1

        # advisory-judge: abstain is not a disagreement
        if isinstance(advisory_judge, dict):
            judge_verdict = advisory_judge.get("verdict")
            if judge_verdict == "abstain":
                advisory_abstains += 1
            elif judge_verdict in ("admit", "reject") and judge_verdict != verdict:
                advisory_disagreements += 1

        # per-tier bucketing
        tier_key = source_tier if source_tier else "unknown"
        if tier_key not in by_tier:
            by_tier[tier_key] = {"admitted": 0, "rejected": 0}
        if verdict == "admit":
            by_tier[tier_key]["admitted"] += 1
        else:
            by_tier[tier_key]["rejected"] += 1

        # reason histogram — collapse variable URL/literal detail
        for reason in reasons:
            cat = _reason_category(reason)
            reason_counts[cat] = reason_counts.get(cat, 0) + 1

    # Ensure official + community always present in by_tier; sort for byte stability
    for tier in _KNOWN_TIERS:
        if tier not in by_tier:
            by_tier[tier] = {"admitted": 0, "rejected": 0}

    if total == 0:
        admit_rate = 0.0
        ev_complete_rate = 0.0
    else:
        admit_rate = round(admitted / total * 100, 1)
        ev_complete_rate = round(evidence_complete_count / total * 100, 1)

    return {
        "admitted": admitted,
        "admit_rate_pct": admit_rate,
        "advisory_judge_abstains": advisory_abstains,
        "advisory_judge_disagreements": advisory_disagreements,
        "by_tier": dict(sorted(by_tier.items())),
        "evidence_complete_pct": ev_complete_rate,
        "reason_histogram": dict(sorted(reason_counts.items())),
        "rejected": rejected,
        "total": total,
    }


def register_cli_subparsers(sub: Any) -> None:
    """Register ``measure-enrich`` onto the orchestrator CLI parser."""
    p = sub.add_parser("measure-enrich")
    p.add_argument(
        "--candidates",
        required=True,
        dest="candidates",
        help=(
            "Path to a JSON file (single candidate object or list) "
            "or a directory whose *.json files are each a candidate."
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="output JSON (always true; flag kept for compat)",
    )
    p.set_defaults(func=cmd_measure_enrich)


def cmd_measure_enrich(args: Any) -> int:
    """CLI handler: measure gate precision over a candidates file or directory."""
    candidates_path = Path(getattr(args, "candidates")).resolve()

    try:
        candidates = _load_candidates(candidates_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error loading candidates from {candidates_path}: {exc}\n")
        return 2

    result = measure(candidates)
    print(json.dumps(result, sort_keys=True))
    return 0
