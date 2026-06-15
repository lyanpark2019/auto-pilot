"""Deterministic escalation-ledger seeder — synthetic record producer for harness use.

Writes N schema-valid escalation records with a known state/problem-class
distribution so the measure-escalation instrument can be exercised and
measured without a real session.

IMPORTANT: seeded records are SYNTHETIC — they validate the instrument and
distribution logic, not real-world escalation rates.  Records are written to
the HOME ledger (~/.claude/projects/<slug>/escalations/), namespaced by the
repo-root slug.  This is NOT filesystem-isolated: two different --repo-root
values with the same slug write to the same ledger directory.  To avoid
polluting the real HOME store, pass a throwaway --repo-root (e.g. a tmp_path)
to get a distinct slug, and clean ~/.claude/projects/<that-slug>/ afterward.

No datetime.now() / random in library functions — ``now`` is a required
caller parameter.  ``cmd_escalation_seed`` may call datetime.now(timezone.utc).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import _contract
from _escalation import (
    _PROBLEM_CLASS_CHOICES,
    compute_fingerprint,
    ledger_dir,
    validate_escalation,
)
from _improvement import PLUGIN_VERSION


# ---------------------------------------------------------------------------
# Pure builder
# ---------------------------------------------------------------------------


def build_seed_records(
    *,
    count: int,
    resolved: int,
    abandoned: int,
    enriched: int,
    now: datetime,
    problem_classes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build N deterministic schema-valid escalation records.

    State split: exactly ``resolved`` resolved + ``abandoned`` abandoned +
    ``enriched`` enriched, remainder open.  Validates the sum ≤ count.
    problem_classes are spread round-robin (default: _PROBLEM_CLASS_CHOICES).

    Returns a list of record dicts; every record passes validate_escalation.
    """
    if resolved + abandoned + enriched > count:
        raise ValueError(
            f"resolved({resolved}) + abandoned({abandoned}) + enriched({enriched}) "
            f"= {resolved + abandoned + enriched} > count({count})"
        )
    if count < 1:
        raise ValueError(f"count must be ≥ 1, got {count}")

    classes = problem_classes if problem_classes else _PROBLEM_CLASS_CHOICES
    repo_fp = "seed-synthetic-repo"
    records: list[dict[str, Any]] = []

    # Assign states in order: resolved first, then abandoned, then enriched, then open.
    state_sequence: list[str] = (
        ["resolved"] * resolved
        + ["abandoned"] * abandoned
        + ["enriched"] * enriched
        + ["open"] * (count - resolved - abandoned - enriched)
    )

    for i, state in enumerate(state_sequence):
        problem_class = classes[i % len(classes)]
        query = f"seed query {i}"
        fp = compute_fingerprint(problem_class, query)
        ts_seen = (now + timedelta(seconds=i)).isoformat().replace("+00:00", "Z")
        ts_last = (now + timedelta(seconds=i, minutes=1)).isoformat().replace("+00:00", "Z")

        record: dict[str, Any] = {
            "schema_version": 1,
            "fingerprint": fp,
            "state": state,
            "problem_class": problem_class,
            "tried": [{"approach": "seed", "outcome": f"seed-{state}"}],
            "evidence": [{"run_id": f"seed-run-{i}", "snippet": f"seed snippet {i}"}],
            "suggested_enrich_query": query,
            "first_seen": ts_seen,
            "last_seen": ts_last,
            "occurrences": 1,
            "distinct_runs": 1,
            "plugin_version": PLUGIN_VERSION,
            "repo_fingerprint": repo_fp,
        }

        if state in ("resolved", "abandoned"):
            record["resolved_at"] = ts_last

        if state in ("enriched", "resolved"):
            # enrichment block — needed for schema validation (enriched requires it).
            record["enrichment"] = {
                "query": query,
                "enriched_at": ts_last,
                "retrieved_date": now.date().isoformat(),
                "counts": {
                    "admitted": 1,
                    "rejected": 0,
                    "written": 1,
                    "unchanged": 0,
                },
            }

        validate_escalation(record)
        records.append(record)

    return records


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


def _write_records(records: list[dict[str, Any]], repo_root: Path) -> int:
    """Write each record via atomic_write_text to ledger_dir(repo_root, None)/<fp>.json.

    Creates the directory if needed.  Returns the count of records written.
    """
    led = ledger_dir(repo_root, None)
    led.mkdir(parents=True, exist_ok=True)
    for record in records:
        fp = record["fingerprint"]
        dest = led / f"{fp}.json"
        _contract.atomic_write_text(dest, json.dumps(record, indent=2, sort_keys=True) + "\n")
    return len(records)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def register_cli_subparsers(sub: Any) -> None:
    """Register ``escalation-seed`` onto the orchestrator CLI parser.

    SYNTHETIC: seeded records validate the instrument + distribution logic,
    NOT real-world rates.  Records are written to the HOME ledger
    (~/.claude/projects/<slug>/escalations/), namespaced by the repo-root slug.
    Use a throwaway --repo-root to get a distinct slug; clean the slug dir
    from ~/.claude/projects/ afterward if persistence is unwanted.
    """
    p = sub.add_parser(
        "escalation-seed",
        help=(
            "Write N SYNTHETIC escalation records for instrument testing. "
            "NOT real-world data — use an isolated --repo-root."
        ),
    )
    p.add_argument("--count", type=int, required=True, help="Total records to seed.")
    p.add_argument(
        "--resolved-pct",
        type=int,
        default=0,
        dest="resolved_pct",
        help="Percentage of records to mark resolved (integer 0-100).",
    )
    p.add_argument(
        "--abandoned-pct",
        type=int,
        default=0,
        dest="abandoned_pct",
        help="Percentage of records to mark abandoned (integer 0-100).",
    )
    p.add_argument(
        "--enriched-pct",
        type=int,
        default=0,
        dest="enriched_pct",
        help="Percentage of records to mark enriched (integer 0-100).",
    )
    p.add_argument(
        "--repo-root",
        required=True,
        dest="repo_root",
        help=(
            "REQUIRED: repo root whose slug names the HOME ledger directory "
            "(~/.claude/projects/<slug>/escalations/). "
            "Use a throwaway path to get a distinct slug and avoid polluting "
            "the real project's ledger; clean ~/.claude/projects/<that-slug>/ afterward."
        ),
    )
    p.add_argument(
        "--now",
        default="2026-06-15T00:00:00Z",
        dest="now",
        help="ISO 8601 datetime for seed timestamps (default: 2026-06-15T00:00:00Z).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print summary only; write nothing to disk.",
    )
    p.set_defaults(func=cmd_escalation_seed)


def cmd_escalation_seed(args: Any) -> int:
    """CLI handler: seed the escalation ledger with synthetic records."""
    import math  # noqa: PLC0415
    import sys  # noqa: PLC0415

    count: int = args.count
    resolved_pct: int = getattr(args, "resolved_pct", 0)
    abandoned_pct: int = getattr(args, "abandoned_pct", 0)
    enriched_pct: int = getattr(args, "enriched_pct", 0)

    resolved = math.floor(count * resolved_pct / 100)
    abandoned = math.floor(count * abandoned_pct / 100)
    enriched = math.floor(count * enriched_pct / 100)

    repo_root = Path(args.repo_root).resolve()
    now_str: str = args.now
    try:
        now = datetime.fromisoformat(now_str.replace("Z", "+00:00"))
    except ValueError as exc:
        print(f"error: invalid --now value {now_str!r}: {exc}", file=sys.stderr)
        return 1

    try:
        records = build_seed_records(
            count=count,
            resolved=resolved,
            abandoned=abandoned,
            enriched=enriched,
            now=now,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    by_state: dict[str, int] = {}
    for rec in records:
        s = rec["state"]
        by_state[s] = by_state.get(s, 0) + 1

    summary = {"count": count, "by_state": by_state, "written": 0 if args.dry_run else count}

    if not args.dry_run:
        written = _write_records(records, repo_root)
        summary["written"] = written

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0
