#!/usr/bin/env python3
"""learning_miner.py — scan reviewer findings + doom-loop signals, bump the
durable per-project ledger, and emit a promotable/thin gate verdict.

Mirrors scripts/risk_assess.py: deterministic Python, no LLM, advisory exit 0
unless --fail-on promotable and verdict is promotable → exit 2.

Output: single-line JSON on stdout —
  {"verdict":"promotable|thin","candidates":N,"promotable_count":M,"by_asset":{...}}
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

import _improvement as imp
from _improvement import Observation
from _log import event

PROMOTION_THRESHOLDS: dict[str, int] = {
    "reviewer-finding": 2,
    "doom-loop": 3,
    "pivot": 3,
    "wasted-tool": 3,
    "insight": 3,
}

# A legacy JSONL line (written before the run_id stamp, or by agent prose) has no
# run_id. Crediting it to the live state run_id lets a single persisted line be
# re-mined under a fresh run_id each run → false distinct_runs inflation. All such
# lines collapse to ONE synthetic run instead, so legacy evidence contributes at
# most 1 to distinct_runs and can never on its own clear a promotion gate.
_LEGACY_RUN_ID = "__legacy_no_run_id__"

# Mirrors candidate_asset enum in schemas/improvement-ticket.schema.json (SoT).
# A producer-written value outside this set is coerced to None so a
# mis-classified finding still becomes a ticket instead of being dropped on
# ValidationError.
VALID_ASSET_TYPES: frozenset[str] = frozenset(
    {"skill", "hook", "schema", "test", "doc", "cache"}
)

# Mirrors the findings[].class enum in schemas/review.schema.json (SoT).
# R1 fix: a reviewer-finding's fingerprint keys on this controlled-vocab class
# instead of the free `issue` prose, so the SAME defect phrased differently
# across runs collapses to ONE ticket and distinct_runs can accumulate to the
# promotion gate. A line whose `class` is absent or outside this set falls back
# to the issue text (legacy/unclassified findings keep working unchanged).
REVIEWER_FINDING_CLASSES: frozenset[str] = frozenset(
    {
        "index-out-of-bounds", "null-deref", "unguarded-empty-input",
        "off-by-one", "unchecked-return", "resource-leak", "race-condition",
        "injection", "missing-input-validation", "incorrect-error-handling",
        "type-confusion", "scope-violation", "missing-test",
        "spec-noncompliance", "doc-drift", "dead-code",
    }
)


def current_run_id(repo_root: Path) -> str:
    """Return state.json 'run_id'; '' if absent, non-string, non-dict, or unparseable."""
    state_path = repo_root / ".planning" / "auto-pilot" / "state.json"
    try:
        data = json.loads(state_path.read_text())
        if not isinstance(data, dict):
            return ""
        val = data.get("run_id", "")
        if not isinstance(val, str):
            return ""
        return val
    except (OSError, json.JSONDecodeError, ValueError):
        return ""


def scan_reviewer_findings(repo_root: Path, run_id: str) -> list[Observation]:
    """Parse critic-rejections-phase-*.jsonl → Observations.

    The fingerprint keys on a reviewer-emitted controlled-vocab ``class`` (the
    review.schema.json findings enum) when present and valid, else on the free
    ``issue`` text — so the same recurring defect, phrased differently each run,
    collapses to one ticket and ``distinct_runs`` can reach the promotion gate.
    """
    planning = repo_root / ".planning" / "auto-pilot"
    observations: list[Observation] = []
    for jsonl_path in sorted(planning.glob("critic-rejections-phase-*.jsonl")):
        try:
            lines = jsonl_path.read_text().splitlines()
        except OSError:
            continue
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                finding = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(finding, dict):
                continue
            file_val = finding.get("file", "")
            issue_val = finding.get("issue", "")
            candidate_val = finding.get("candidate_asset")
            if not isinstance(file_val, str):
                file_val = str(file_val)
            if not isinstance(issue_val, str):
                issue_val = str(issue_val)
            if candidate_val is not None and not isinstance(candidate_val, str):
                candidate_val = str(candidate_val)
            if candidate_val not in VALID_ASSET_TYPES:
                candidate_val = None
            # R1 fix: key the fingerprint on the controlled-vocab `class` when the
            # reviewer emitted a valid one; else fall back to the free issue text.
            # The fingerprint seeds on Observation.issue, so a valid class makes
            # the SAME defect phrased differently collapse to ONE ticket (basename
            # is kept, so the same class in a different file stays a distinct one).
            class_val = finding.get("class")
            keyed_issue = (
                class_val
                if isinstance(class_val, str) and class_val in REVIEWER_FINDING_CLASSES
                else issue_val
            )
            snippet = json.dumps(finding)[:500]
            # Use the line's own run_id (stamped at capture time) so that
            # re-mining the same JSONL under a new state run_id does not
            # inflate distinct_runs for observations from prior runs.
            # Legacy lines (no run_id key) collapse to a single synthetic run
            # (_LEGACY_RUN_ID) — NOT the live state run_id, which would let one
            # persisted line accrue a fresh distinct run each mine.
            line_run_id = finding.get("run_id")
            effective_run_id = (
                line_run_id
                if isinstance(line_run_id, str) and line_run_id.strip()
                else _LEGACY_RUN_ID
            )
            observations.append(
                Observation(
                    source="reviewer-finding",
                    file_basename=Path(file_val).name if file_val else "",
                    issue=keyed_issue,
                    candidate_asset=candidate_val,
                    run_id=effective_run_id,
                    snippet=snippet,
                    source_path=file_val,
                )
            )
    return observations


def scan_doom_loops(repo_root: Path, run_id: str) -> list[Observation]:
    """Parse state.json pivot_detector buckets (value>=1) → Observations."""
    state_path = repo_root / ".planning" / "auto-pilot" / "state.json"
    observations: list[Observation] = []
    try:
        data = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return observations
    pivot_detector = data.get("pivot_detector")
    if not isinstance(pivot_detector, dict):
        return observations
    # pivot_detector is NESTED: {"phase-N": {"finding_hash": count}} per _state.py TypedDict.
    # The old code iterated the outer dict and called int() on the inner dict value,
    # raising TypeError (caught silently) → every doom-loop entry was dropped.
    for phase_key, findings in pivot_detector.items():
        if not isinstance(findings, dict):
            continue
        for finding_hash, count in findings.items():
            try:
                count_int = int(count)
            except (TypeError, ValueError):
                continue
            if count_int < 1:
                continue
            snippet = json.dumps(
                {"phase": phase_key, "finding_hash": finding_hash, "count": count_int}
            )[:500]
            observations.append(
                Observation(
                    source="doom-loop",
                    file_basename="",
                    issue="doom-loop",
                    candidate_asset=None,
                    run_id=run_id,
                    snippet=snippet,
                )
            )
    return observations


def scan_insights(repo_root: Path, run_id: str) -> list[Observation]:
    """Parse insights.jsonl → class-keyed Observations (source='insight').

    The fingerprint keys on the canonical ``class`` tag with an empty
    ``file_basename`` so a recurring class accumulates ``distinct_runs`` across
    sessions even when the human one-liner is reworded each time (measurement:
    classes recur across many session-days, the wording does not). A line with
    no usable ``class`` falls back to its ``issue`` text; with neither it is
    skipped. Malformed / non-dict lines are tolerated (degrade, never crash).
    """
    path = repo_root / ".planning" / "auto-pilot" / "insights.jsonl"
    observations: list[Observation] = []
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return observations
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            finding = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(finding, dict):
            continue
        class_val = finding.get("class")
        issue_val = finding.get("issue", "")
        if not (isinstance(class_val, str) and class_val.strip()):
            class_val = issue_val if isinstance(issue_val, str) else ""
        if not class_val.strip():
            continue
        # A path/date-shaped tag normalizes to "" inside compute_fingerprint;
        # keying on it would collapse unrelated insights into one ticket (the
        # exact fragmentation this source exists to prevent). Skip such a tag.
        if not imp.normalize_issue(class_val).strip():
            continue
        candidate_val = finding.get("candidate_asset")
        if candidate_val is not None and not isinstance(candidate_val, str):
            candidate_val = str(candidate_val)
        if candidate_val not in VALID_ASSET_TYPES:
            candidate_val = None
        observations.append(
            Observation(
                source="insight",
                file_basename="",
                issue=class_val,
                candidate_asset=candidate_val,
                run_id=run_id,
                snippet=json.dumps(finding)[:500],
            )
        )
    return observations


def _ticket_source(ticket: dict[str, object]) -> str:
    src = ticket.get("source", "")
    return src if isinstance(src, str) else ""


def _ticket_distinct_runs(ticket: dict[str, object]) -> int:
    dr = ticket.get("distinct_runs", 0)
    return dr if isinstance(dr, int) else 0


def is_promotable(ticket: dict[str, object]) -> bool:
    """Return True when ticket's distinct_runs meets its source's promotion threshold."""
    threshold = PROMOTION_THRESHOLDS.get(_ticket_source(ticket))
    if threshold is None:
        return False
    return _ticket_distinct_runs(ticket) >= threshold


_is_promotable = is_promotable  # backward-compat alias


def verdict_for(tickets: list[dict[str, object]]) -> str:
    """'promotable' if any ticket's distinct_runs >= PROMOTION_THRESHOLDS[source], else 'thin'."""
    return "promotable" if any(_is_promotable(t) for t in tickets) else "thin"


def run_miner(
    repo_root: Path,
    *,
    commit_to: Path | None,
    now: datetime,
    dry_run: bool,
) -> dict[str, object]:
    """Scan inputs, bump ledger, collect tickets, compute verdict.

    Returns {'verdict', 'candidates', 'promotable_count', 'by_asset'}.
    """
    run_id = current_run_id(repo_root)
    observations: list[Observation] = []
    observations.extend(scan_reviewer_findings(repo_root, run_id))
    observations.extend(scan_doom_loops(repo_root, run_id))
    observations.extend(scan_insights(repo_root, run_id))

    effective_dry_run = dry_run or (not run_id.strip())
    if not run_id.strip() and not dry_run:
        event("learning_miner.non_persisting", reason="empty_run_id", candidates=len(observations))

    ledger = imp.ledger_dir(repo_root, commit_to)

    tickets: list[dict[str, object]] = []
    for obs in observations:
        try:
            ticket = imp.bump_or_create(
                ledger, obs, repo_root=repo_root, now=now, dry_run=effective_dry_run
            )
        except Exception as exc:  # noqa: BLE001 — advisory miner degrades, never aborts the scan
            event("learning_miner.bump_skipped", source=obs.source, error=type(exc).__name__)
            continue
        tickets.append(ticket)

    verdict = verdict_for(tickets)

    promotable_count = sum(1 for t in tickets if _is_promotable(t))

    by_asset: dict[str, int] = defaultdict(int)
    for t in tickets:
        asset_raw = t.get("candidate_asset")
        asset = asset_raw if isinstance(asset_raw, str) else "none"
        by_asset[asset] += 1

    return {
        "verdict": verdict,
        "candidates": len(tickets),
        "promotable_count": promotable_count,
        "by_asset": dict(by_asset),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="learning_miner",
        description="Scan reviewer/doom-loop signals, bump ledger, emit gate verdict.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        metavar="PATH",
        help="root of the target repo (default: cwd)",
    )
    parser.add_argument(
        "--commit-to",
        default=None,
        metavar="PATH",
        help="opt-in: write ledger to this tracked path instead of ~/.claude/projects/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="compute projected counts; write nothing",
    )
    parser.add_argument(
        "--fail-on",
        choices=["promotable"],
        default=None,
        help="exit 2 when verdict matches (CI wiring)",
    )
    parser.add_argument(
        "--json",
        dest="json_only",
        action="store_true",
        help="suppress human report; print only the JSON line",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Argparse CLI entry point.  Returns exit code (0 or 2)."""
    args = _build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    commit_to = Path(args.commit_to).resolve() if args.commit_to else None
    now = datetime.now(timezone.utc)

    result = run_miner(repo_root, commit_to=commit_to, now=now, dry_run=args.dry_run)

    verdict_line = json.dumps(result, sort_keys=False)
    if not args.json_only:
        sys.stdout.write(
            f"learning_miner: verdict={result['verdict']} "
            f"candidates={result['candidates']} "
            f"promotable={result['promotable_count']}\n"
        )
    sys.stdout.write(verdict_line + "\n")

    if args.fail_on == "promotable" and result["verdict"] == "promotable":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
