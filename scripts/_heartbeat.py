"""Reviewer heartbeat: outputs/<role>/status.json writes + PM-side rendering.

Mirrors the existing worker-status pattern (workers write
outputs/worker/status.json) so the PM is not blind between dispatch and
done.marker. Documented shape, no JSON schema: role, started_at, elapsed_s,
last_beat, phase, risk_tier. Written at reviewer start and on every codex
retry/transition (scripts/codex_review_bounded.py imports write_beat).

Residual (spec): the interactive PM dispatches reviewers via the BLOCKING
Agent tool — beats are pollable mid-flight only from the headless path or a
parallel monitor; a blocking round sees the trail on return.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _contract
import _evidence

STATUS_NAME = "status.json"
_NO_STATUS = "no reviewer status files for the active round"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.isoformat(timespec="seconds")


def write_beat(
    out_dir: Path,
    role: str,
    phase: str,
    risk_tier: str | None = None,
) -> Path:
    """Write/refresh <out_dir>/status.json, preserving the first started_at."""
    target = out_dir / STATUS_NAME
    started_at: str = ""
    if target.exists():
        try:
            parsed = json.loads(target.read_text())
            if isinstance(parsed, dict):
                started_at = str(parsed.get("started_at") or "")
        except (json.JSONDecodeError, OSError):
            started_at = ""
    now = _now()
    if not started_at:
        started_at = _iso(now)
    try:
        elapsed = max(
            int((now - datetime.fromisoformat(started_at)).total_seconds()), 0
        )
    except (ValueError, TypeError):
        started_at, elapsed = _iso(now), 0
    payload: dict[str, Any] = {
        "role": role,
        "started_at": started_at,
        "elapsed_s": elapsed,
        "last_beat": _iso(now),
        "phase": phase,
        "risk_tier": risk_tier,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    return _contract.atomic_write_text(
        target, json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )


def _round_rows(round_dir: Path, root: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for status_file in sorted(round_dir.glob(f"outputs/*/{STATUS_NAME}")):
        try:
            data = json.loads(status_file.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        try:
            beat_age = int(
                (
                    _now()
                    - datetime.fromisoformat(str(data.get("last_beat") or ""))
                ).total_seconds()
            )
            age = f"{beat_age}s"
        except (ValueError, TypeError):
            age = "?"
        done = "yes" if (status_file.parent / "done.marker").exists() else "no"
        rows.append(
            [
                str(round_dir.relative_to(root)),
                str(data.get("role") or status_file.parent.name),
                str(data.get("phase") or "?"),
                str(data.get("risk_tier") or "-"),
                f"{data.get('elapsed_s', '?')}s",
                age,
                done,
            ]
        )
    return rows


def render_table(contracts_root: Path) -> str:
    """Compact reviewer-status table for the active phase's latest rounds."""
    header = ["round", "role", "phase", "tier", "elapsed", "beat-age", "done"]
    rows: list[list[str]] = []
    for round_dir in _evidence.latest_round_dirs_for_active_phase(contracts_root):
        rows.extend(_round_rows(round_dir, contracts_root))
    if not rows:
        return _NO_STATUS
    widths = [
        max(len(r[i]) for r in [header, *rows]) for i in range(len(header))
    ]
    lines = [
        "  ".join(c.ljust(widths[i]) for i, c in enumerate(r))
        for r in [header, *rows]
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: `_heartbeat.py beat --out-dir D --role R --phase P [--risk-tier T]`."""
    parser = argparse.ArgumentParser(prog="_heartbeat")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_beat = sub.add_parser("beat")
    p_beat.add_argument("--out-dir", required=True)
    p_beat.add_argument("--role", required=True)
    p_beat.add_argument("--phase", required=True)
    p_beat.add_argument("--risk-tier", default=None)
    args = parser.parse_args(argv)
    write_beat(Path(args.out_dir), args.role, args.phase, risk_tier=args.risk_tier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
