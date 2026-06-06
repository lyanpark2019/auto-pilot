"""Corpus selection + aggregation of OracleResults into a results summary."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evals._types import CaseAttempt


def select_cases(cases_dir: Path, tier: str) -> list[str]:
    """Return case ids whose meta tags include ``tier`` (``full`` selects all)."""
    out: list[str] = []
    for meta_path in sorted(cases_dir.glob("*/meta.json")):
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed meta.json: {meta_path}") from exc
        tags = set(meta.get("tags", []))
        if tier == "full" or tier in tags:
            out.append(meta_path.parent.name)
    return out


def summarize(case_id: str, attempts: list[CaseAttempt]) -> dict[str, Any]:
    """Aggregate per-case attempts. error counts toward total_attempted (non-pass)."""
    passed = sum(1 for a in attempts if a.oracle.outcome == "pass")
    failed = sum(1 for a in attempts if a.oracle.outcome == "fail")
    errored = sum(1 for a in attempts if a.oracle.outcome == "error")
    n = len(attempts)
    return {
        "case": case_id,
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "attempts": n,
        "pass_rate": (passed / n) if n else 0.0,
        "cost_usd": round(sum(a.run.cost_usd for a in attempts), 4),
        "reasons": [a.oracle.reason for a in attempts if a.oracle.outcome != "pass"],
    }


def write_results(
    path: Path, run_id: str, summaries: list[dict[str, Any]],
    meta: dict[str, Any] | None = None,
) -> None:
    """Write ``summaries`` to ``path`` as JSON under a ``run_id`` envelope."""
    payload: dict[str, Any] = {**(meta or {}), "run_id": run_id, "cases": summaries}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
