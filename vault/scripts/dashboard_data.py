#!/usr/bin/env python3
"""Generate dashboard/data.json from vault meta/*.

Usage:
    python3 scripts/dashboard_data.py <vault> [--out dashboard/data.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def collect(vault: Path) -> dict:
    meta = vault / "meta"
    out: dict = {"vault": str(vault), "vault_name": vault.name}

    def _load(p: Path) -> dict | None:
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"dashboard_data: failed to load {p}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return None

    out["structural"] = _load(meta / "score-state.json")
    out["content"] = _load(meta / "score-content-state.json")
    out["tickets"] = _load(meta / "ticket-state.json")

    audits = []
    for p in sorted(meta.glob("audit-r*.md")):
        audits.append({"file": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime})
    out["structural_audits"] = audits

    content_audits = []
    for p in sorted(meta.glob("content-audit-r*.md")):
        content_audits.append({"file": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime})
    out["content_audits"] = content_audits

    rounds = []
    for p in sorted(meta.glob("pm-round-*.md")):
        rounds.append({"file": p.name, "mtime": p.stat().st_mtime})
    out["pm_rounds"] = rounds

    cost_log = meta / "_cost" / "cost-log.jsonl"
    if cost_log.exists():
        entries = []
        for line in cost_log.read_text().splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    print(f"dashboard_data: skipping corrupt JSONL line in {cost_log}: {type(exc).__name__}: {exc}", file=sys.stderr)
                    continue
        out["cost_log"] = entries

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("vault", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    vault = args.vault.expanduser().resolve()
    data = collect(vault)
    out_path = args.out or (Path(__file__).resolve().parent.parent / "dashboard" / "data.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
