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


def current_run_id(repo_root: Path) -> str:
    """Return state.json 'run_id'; '' if absent or unparseable."""
    state_path = repo_root / ".planning" / "auto-pilot" / "state.json"
    try:
        data = json.loads(state_path.read_text())
        return str(data.get("run_id", ""))
    except (OSError, json.JSONDecodeError, ValueError):
        return ""


def scan_reviewer_findings(repo_root: Path, run_id: str) -> list[Observation]:
    """Parse critic-rejections-phase-*.jsonl → Observations."""
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
            snippet = json.dumps(finding)[:500]
            observations.append(
                Observation(
                    source="reviewer-finding",
                    file_basename=Path(file_val).name if file_val else "",
                    issue=issue_val,
                    candidate_asset=candidate_val if candidate_val else None,
                    run_id=run_id,
                    snippet=snippet,
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
    for phase_key, count in pivot_detector.items():
        try:
            count_int = int(count)
        except (TypeError, ValueError):
            continue
        if count_int < 1:
            continue
        snippet = json.dumps({"phase": phase_key, "count": count_int})[:500]
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


def _ticket_source(ticket: dict[str, object]) -> str:
    src = ticket.get("source", "")
    return src if isinstance(src, str) else ""


def _ticket_distinct_runs(ticket: dict[str, object]) -> int:
    dr = ticket.get("distinct_runs", 0)
    return dr if isinstance(dr, int) else 0


def _is_promotable(ticket: dict[str, object]) -> bool:
    threshold = PROMOTION_THRESHOLDS.get(_ticket_source(ticket))
    if threshold is None:
        return False
    return _ticket_distinct_runs(ticket) >= threshold


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

    ledger = imp.ledger_dir(repo_root, commit_to)

    tickets: list[dict[str, object]] = []
    for obs in observations:
        try:
            ticket = imp.bump_or_create(
                ledger, obs, repo_root=repo_root, now=now, dry_run=dry_run
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
