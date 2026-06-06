#!/usr/bin/env python3
"""Drift → PM ticket plan.

Reads drift report (or runs detection live), maps each drift entry to the
appropriate worker, emits ticket plan JSON. PM agent reads the plan and
dispatches workers in parallel.

Drift type → worker:
- gap          → vault-knowledge-author  (create new doc page from public_api scan)
- orphan       → vault-structure-curator (remove dead refs / mark stale)
- claim_drift  → vault-knowledge-author  (update signature in doc to match code)
- symbol_drift → vault-knowledge-author  (replace stale symbol with current)

This script does NOT call Agent. It produces a plan PM consumes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

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


def build_plan(repo: Path, doc_root: Path | None = None, max_per_type: int = 50) -> dict:
    repo = repo.expanduser().resolve()
    doc_root = (doc_root or repo).expanduser().resolve()

    report = drift_mod.detect(repo, doc_root)
    report_dict = report.to_dict()

    plan: dict = {
        "schema_version": 1,
        "generated_at": time.time(),
        "repo": str(repo),
        "doc_root": str(doc_root),
        "drift_summary": report_dict["summary"],
        "tickets": [],
    }

    def _ticket(worker: str, drift_type: str, items: list[dict]) -> dict:
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

    # Group drift entries per type; emit one ticket per type per doc (workers iterate)
    by_doc: dict[tuple[str, str], list[dict]] = {}
    for drift_type in ("gap", "orphan", "claim_drift", "symbol_drift"):
        for item in report_dict[drift_type]:
            doc_key = item.get("doc") or item.get("module") or "_global"
            by_doc.setdefault((drift_type, doc_key), []).append(item)

    for (drift_type, doc_key), items in by_doc.items():
        worker = WORKER_FOR_DRIFT[drift_type]
        plan["tickets"].append(_ticket(worker, drift_type, items))

    return plan


def main(argv: list[str]) -> int:
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
    print(json.dumps({
        "wrote": str(out),
        "tickets": len(plan["tickets"]),
        "drift_summary": plan["drift_summary"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
