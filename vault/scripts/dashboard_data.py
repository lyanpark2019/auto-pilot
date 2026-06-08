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
from typing import Any


def _write_line(stream, message: str) -> None:
    stream.write(f"{message}\n")


def _emit(message: str) -> None:
    _write_line(sys.stdout, message)


def _warn(message: str) -> None:
    _write_line(sys.stderr, message)


def _load_json(p: Path) -> dict[str, Any] | None:
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _warn(f"dashboard_data: failed to load {p}: {type(exc).__name__}: {exc}")
        return None
    return data if isinstance(data, dict) else None


def _audit_records(meta: Path, pattern: str, *, include_size: bool) -> list[dict[str, Any]]:
    records = []
    for p in sorted(meta.glob(pattern)):
        row: dict[str, Any] = {"file": p.name, "mtime": p.stat().st_mtime}
        if include_size:
            row["size"] = p.stat().st_size
        records.append(row)
    return records


def _cost_entries(cost_log: Path) -> list[dict[str, Any]] | None:
    if not cost_log.exists():
        return None
    entries = []
    for line in cost_log.read_text().splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            _warn(f"dashboard_data: skipping corrupt JSONL line in {cost_log}: {type(exc).__name__}: {exc}")
            continue
        if isinstance(data, dict):
            entries.append(data)
    return entries


def collect(vault: Path) -> dict[str, Any]:
    meta = vault / "meta"
    out: dict[str, Any] = {"vault": str(vault), "vault_name": vault.name}
    out["structural"] = _load_json(meta / "score-state.json")
    out["content"] = _load_json(meta / "score-content-state.json")
    out["tickets"] = _load_json(meta / "ticket-state.json")
    out["structural_audits"] = _audit_records(meta, "audit-r*.md", include_size=True)
    out["content_audits"] = _audit_records(meta, "content-audit-r*.md", include_size=True)
    out["pm_rounds"] = _audit_records(meta, "pm-round-*.md", include_size=False)
    entries = _cost_entries(meta / "_cost" / "cost-log.jsonl")
    if entries is not None:
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
    _emit(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
