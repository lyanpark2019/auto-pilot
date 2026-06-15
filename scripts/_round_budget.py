"""Round-budget gate helpers + CLI handler for orchestrator.py.

Pure loaders (load_findings / count_findings) were extracted from orchestrator.py
when the review-status subcommand was added (2026-06-12). The CLI handler
(_emit_hard_stop / cmd_round_budget / register_cli_subparsers) followed when
the round-budget inline block was extracted to restore orchestrator.py headroom.
"""
from __future__ import annotations

import argparse
import json
import sys
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


def _emit_hard_stop(n: int, c_prev: int, c_curr: int) -> int:
    """Print HARD-STOP verdict to stdout+stderr and return exit 3."""
    msg = "HARD-STOP: 전략 전환 필요"
    print(json.dumps({
        "round": n, "count_prev": c_prev, "count_curr": c_curr, "verdict": msg,
    }, indent=2))
    print(msg, file=sys.stderr)
    return 3


def cmd_round_budget(args: argparse.Namespace) -> int:
    """Deterministic gate: check whether the review round budget is exhausted.

    Reads findings-round-{N-1,N}.json from ``--score-dir``.  Rules:
      N < 3  → exit 0 informational.
      N == 3, count(N) >= count(N-1)  → exit 3 HARD-STOP.
      N == 3, count(N) < count(N-1)   → exit 0 "round 4 = final cap".
      Missing file → exit 2.

    Returns 0 (ok/informational), 2 (missing file), or 3 (HARD-STOP).
    """
    score_dir = Path(args.score_dir)
    n = args.round
    if n < 3:
        data_n = load_findings(score_dir, n)
        if not data_n:
            return 2
        c = count_findings(data_n)
        print(json.dumps({"round": n, "count": c, "status": "informational"}, indent=2))
        return 0
    data_prev = load_findings(score_dir, n - 1)
    data_curr = load_findings(score_dir, n)
    if not data_prev or not data_curr:
        return 2
    c_prev = count_findings(data_prev)
    c_curr = count_findings(data_curr)
    if c_curr >= c_prev:
        return _emit_hard_stop(n, c_prev, c_curr)
    print(json.dumps({
        "round": n, "count_prev": c_prev, "count_curr": c_curr,
        "verdict": "round 4 = final cap",
    }, indent=2))
    return 0


def register_cli_subparsers(sub: Any) -> None:
    """Register the ``round-budget`` subparser onto ``sub``."""
    p = sub.add_parser("round-budget")
    p.add_argument("--score-dir", required=True)
    p.add_argument("--round", type=int, required=True)
    p.set_defaults(func=cmd_round_budget)
