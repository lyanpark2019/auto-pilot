#!/usr/bin/env python3
"""auto-pilot orchestrator helper.

The actual PM loop runs in the Claude Code main session (Opus 4.7) — this file
is a state-management and reporting helper invoked by the skill/command. It does
NOT itself dispatch agents (only the main session can call the Agent tool).

Usage:
    python orchestrator.py init  --spec docs/specs/X.md --max-workers 10
    python orchestrator.py phase-start  --phase 1 --contracts 6
    python orchestrator.py phase-end    --phase 1 --status success --commits sha1,sha2
    python orchestrator.py pivot-check  --phase 1 --finding-hash abc123
    python orchestrator.py status
    python orchestrator.py stop
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(".planning/auto-pilot")
STATE_FILE = STATE_DIR / "state.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text())


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


def cmd_init(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"ERROR: spec not found: {spec_path}", file=sys.stderr)
        return 2

    existing = load_state()
    if existing.get("status") == "running" and not args.force:
        print(
            "ERROR: state.json already running — pass --force to wipe, or `stop` first",
            file=sys.stderr,
        )
        return 2

    total_phases = _count_phases(spec_path)

    state = {
        "started_at": utc_now(),
        "spec_path": str(spec_path),
        "current_phase": 0,
        "total_phases": total_phases,
        "status": "running",
        "max_workers": args.max_workers,
        "time_box_until": args.time_box_until,
        "phases": [],
        "pivot_detector": {},
    }
    save_state(state)
    print(json.dumps({"ok": True, "state": state}, indent=2))
    return 0


def cmd_phase_start(args: argparse.Namespace) -> int:
    state = load_state()
    if not state:
        print("ERROR: no state — run init first", file=sys.stderr)
        return 2

    state["current_phase"] = args.phase
    state["phases"].append({
        "phase": args.phase,
        "status": "running",
        "round": 1,
        "contracts": args.contracts,
        "approved": 0,
        "started": utc_now(),
        "ended": None,
        "commits": [],
    })
    save_state(state)
    print(json.dumps({"ok": True, "phase": args.phase}, indent=2))
    return 0


def cmd_phase_end(args: argparse.Namespace) -> int:
    state = load_state()
    if not state or not state.get("phases"):
        print("ERROR: no active phase", file=sys.stderr)
        return 2

    current = state["phases"][-1]
    if current["phase"] != args.phase:
        print(
            f"ERROR: --phase {args.phase} does not match active phase {current['phase']}",
            file=sys.stderr,
        )
        return 2
    current["status"] = args.status
    current["ended"] = utc_now()
    current["commits"] = args.commits.split(",") if args.commits else []

    if args.status == "success" and state["current_phase"] >= state["total_phases"]:
        state["status"] = "success"
    elif args.status in ("failed", "pivot-needed"):
        state["status"] = args.status

    save_state(state)
    print(json.dumps({"ok": True, "phase": args.phase, "status": args.status}, indent=2))
    return 0


def cmd_pivot_check(args: argparse.Namespace) -> int:
    """Returns nonzero exit when finding has repeated 3+ times — PM should stop."""
    state = load_state()
    if not state:
        return 0

    bucket = state.setdefault("pivot_detector", {}).setdefault(f"phase-{args.phase}", {})
    bucket[args.finding_hash] = bucket.get(args.finding_hash, 0) + 1
    save_state(state)

    count = bucket[args.finding_hash]
    print(json.dumps({"finding_hash": args.finding_hash, "count": count}))
    if count >= 3:
        print("PIVOT NEEDED: same finding 3 rounds — strategy change required", file=sys.stderr)
        state["status"] = "pivot-needed"
        save_state(state)
        return 1
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    state = load_state()
    if not state:
        print("auto-pilot: not initialized")
        return 0
    print(json.dumps(state, indent=2))
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    state = load_state()
    if not state:
        print("auto-pilot: nothing to stop")
        return 0
    state["status"] = "stopped"
    state["stopped_at"] = utc_now()
    save_state(state)
    print(json.dumps({"ok": True, "status": "stopped"}, indent=2))
    return 0


def _count_phases(spec_path: Path) -> int:
    text = spec_path.read_text()
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Phase ") or stripped.startswith("# Phase "):
            count += 1
    return max(count, 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="auto-pilot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--spec", required=True)
    p_init.add_argument("--max-workers", type=int, default=10)
    p_init.add_argument("--time-box-until", default=None)
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_ps = sub.add_parser("phase-start")
    p_ps.add_argument("--phase", type=int, required=True)
    p_ps.add_argument("--contracts", type=int, required=True)
    p_ps.set_defaults(func=cmd_phase_start)

    p_pe = sub.add_parser("phase-end")
    p_pe.add_argument("--phase", type=int, required=True)
    p_pe.add_argument("--status", choices=["success", "failed", "pivot-needed"], required=True)
    p_pe.add_argument("--commits", default="")
    p_pe.set_defaults(func=cmd_phase_end)

    p_pv = sub.add_parser("pivot-check")
    p_pv.add_argument("--phase", type=int, required=True)
    p_pv.add_argument("--finding-hash", required=True)
    p_pv.set_defaults(func=cmd_pivot_check)

    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("stop").set_defaults(func=cmd_stop)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
