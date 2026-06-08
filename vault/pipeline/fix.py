#!/usr/bin/env python3
"""Drift → PM ticket plan.

Reads drift report (or runs detection live), maps each drift entry to the
appropriate worker, emits ticket plan JSON. PM agent reads the plan and
dispatches workers in parallel.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pipeline import drift as drift_mod
else:
    from pipeline import drift as drift_mod


WORKER_FOR_DRIFT = {
    "gap": "vault-knowledge-author",
    "orphan": "vault-structure-curator",
    "claim_drift": "vault-knowledge-author",
    "symbol_drift": "vault-knowledge-author",
}
DRIFT_TYPES = ("gap", "orphan", "claim_drift", "symbol_drift")


def _emit_json(payload: Any, *, indent: int | None = None) -> None:
    sys.stdout.write(f"{json.dumps(payload, indent=indent)}\n")


def _ticket(worker: str, drift_type: str, items: list[dict[str, Any]], doc_root: Path, repo: Path, max_per_type: int) -> dict[str, Any]:
    return {
        "id": f"T-{drift_type}-{uuid.uuid4().hex[:6]}",
        "worker_type": worker,
        "contract": {
            "goal": f"Fix {len(items)} {drift_type} drift entries",
            "drift_type": drift_type,
            "items": items[:max_per_type],
            "doc_root": str(doc_root),
            "repo": str(repo),
            "reward": 10,
        },
    }


def _group_by_doc(report_dict: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    by_doc: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for drift_type in DRIFT_TYPES:
        for item in report_dict[drift_type]:
            doc_key = item.get("doc") or item.get("module") or "_global"
            by_doc.setdefault((drift_type, str(doc_key)), []).append(item)
    return by_doc


def _plan_header(repo: Path, doc_root: Path, report_dict: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": time.time(),
        "repo": str(repo),
        "doc_root": str(doc_root),
        "drift_summary": report_dict["summary"],
        "tickets": [],
    }


def build_plan(repo: Path, doc_root: Path | None = None, max_per_type: int = 50) -> dict[str, Any]:
    """Build plan artifacts."""
    repo = repo.expanduser().resolve()
    doc_root = (doc_root or repo).expanduser().resolve()
    report_dict = drift_mod.detect(repo, doc_root).to_dict()
    plan = _plan_header(repo, doc_root, report_dict)
    for (drift_type, _doc_key), items in _group_by_doc(report_dict).items():
        plan["tickets"].append(_ticket(WORKER_FOR_DRIFT[drift_type], drift_type, items, doc_root, repo, max_per_type))
    return plan


def main(argv: list[str]) -> int:
    """Run the fix command-line entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--doc-root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--max-per-type", type=int, default=50)
    args = ap.parse_args(argv[1:])

    plan = build_plan(args.repo, args.doc_root, args.max_per_type)
    out = args.out or (args.repo / ".vault-builder" / "fix-plan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    _emit_json({"wrote": str(out), "tickets": len(plan["tickets"]), "drift_summary": plan["drift_summary"]}, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
