#!/usr/bin/env python3
"""Phase 3.5 helper: dispatch claude-obsidian:wiki-ingest per category.

The actual Skill invocation must happen inside Claude Code via the Skill tool.
This script prepares the dispatch plan (sources to ingest, args per cat) that
the orchestrating agent reads to execute parallel Skill calls.

Usage:
    python3 scripts/wiki_ingest_chain.py <vault> [--no-skip-existing]

Output: <vault>/meta/wiki-ingest-plan.json — agent reads this and invokes Skill
tool for each entry in parallel (single message, multiple tool_use blocks).

Plan format:
    {
      "vault": "...",
      "generated_at": <ts>,
      "dispatches": [
        {"cat": "...", "source": "<vault>/<cat>/sources/_index.md", "args": "..."},
        ...
      ]
    }
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def build_plan(vault: Path, skip_existing: bool = True) -> dict:
    dispatches = []
    for cat_dir in sorted(p for p in vault.iterdir() if p.is_dir() and not p.name.startswith(".")):
        sources_idx = cat_dir / "sources" / "_index.md"
        if not sources_idx.exists():
            continue
        log = cat_dir / ".wiki-ingest-log.md"
        if skip_existing and log.exists() and log.stat().st_mtime >= sources_idx.stat().st_mtime:
            continue
        dispatches.append({
            "cat": cat_dir.name,
            "source": str(sources_idx),
            "args": f"--source {sources_idx} --vault {vault} --batch --log {log}",
            "skill": "claude-obsidian:wiki-ingest",
            "expected_log": str(log),
        })
    return {
        "vault": str(vault),
        "generated_at": time.time(),
        "skip_existing": skip_existing,
        "dispatches": dispatches,
        "total": len(dispatches),
        "note": "Agent must invoke Skill tool for each dispatch in parallel (single message). This script does not call Claude; it only plans.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("vault", type=Path)
    ap.add_argument("--no-skip-existing", action="store_true",
                    help="Re-ingest even if .wiki-ingest-log.md is up-to-date")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    vault = args.vault.expanduser().resolve()
    plan = build_plan(vault, skip_existing=not args.no_skip_existing)
    out = args.out or (vault / "meta" / "wiki-ingest-plan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    print(json.dumps({"plan": str(out), "dispatches": plan["total"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
