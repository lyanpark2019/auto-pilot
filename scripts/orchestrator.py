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
import re
from pathlib import Path

from _log import event
from _state import (
    PhaseEntry,
    State,
    load_state,
    save_state,
    utc_now,
)


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new auto-pilot run by writing a fresh state file.

    Args:
        args: parsed CLI namespace; expects ``spec``, ``max_workers``,
            ``time_box_until`` and ``force``.

    Returns:
        0 on success, 2 if the spec is missing or a run is already active.
    """
    spec_path = Path(args.spec)
    if not spec_path.exists():
        event("init.spec_missing", path=spec_path)
        return 2

    existing = load_state()
    if existing.get("status") == "running" and not args.force:
        event("init.already_running", hint="pass --force to wipe or run stop first")
        return 2

    total_phases = _count_phases(spec_path)

    state: State = {
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
    """Begin (or retry) a phase, validating bounds and bumping ``round`` on retry.

    Validation rules:
      - state must be initialized,
      - ``--phase`` must be within ``1..total_phases`` inclusive,
      - if an entry for ``--phase`` is already ``running`` it is refused,
      - if an entry exists in any other status the entry is reused with
        ``round`` incremented, ``status`` reset to ``running``, ``ended``
        cleared, and ``contracts`` overwritten.

    Args:
        args: parsed CLI namespace; expects ``phase`` (int) and ``contracts`` (int).

    Returns:
        0 on success, 2 on any validation failure.
    """
    state = load_state()
    if not state:
        event("phase_start.no_state")
        return 2

    if "run_id" not in state or not state.get("run_id"):
        import uuid
        state["run_id"] = uuid.uuid4().hex

    total = state.get("total_phases", 0)
    if args.phase < 1 or args.phase > total:
        event("phase_start.out_of_range", phase=args.phase, total_phases=total)
        return 2

    phases: list[PhaseEntry] = state.setdefault("phases", [])
    existing = next((p for p in phases if p["phase"] == args.phase), None)
    if existing is not None:
        if existing["status"] == "running":
            event("phase_start.already_running", phase=args.phase)
            return 2
        existing["round"] = existing["round"] + 1
        existing["status"] = "running"
        existing["ended"] = None
        existing["contracts"] = args.contracts
        state["current_phase"] = args.phase
        save_state(state)
        print(
            json.dumps(
                {"ok": True, "phase": args.phase, "round": existing["round"]},
                indent=2,
            )
        )
        return 0

    state["current_phase"] = args.phase
    new_entry: PhaseEntry = {
        "phase": args.phase,
        "status": "running",
        "round": 1,
        "contracts": args.contracts,
        "approved": 0,
        "started": utc_now(),
        "ended": None,
        "commits": [],
    }
    phases.append(new_entry)
    save_state(state)
    print(json.dumps({"ok": True, "phase": args.phase}, indent=2))
    return 0


def cmd_phase_end(args: argparse.Namespace) -> int:
    """Close out the active phase with a final status and commit list.

    Promotes the run's top-level ``status`` to ``success`` only when the last
    spec phase has just ended successfully; otherwise propagates ``failed`` /
    ``pivot-needed`` as-is.

    Args:
        args: parsed CLI namespace; expects ``phase``, ``status``, ``commits``.

    Returns:
        0 on success, 2 if no phase is active or the requested phase does not
        match the currently-running one.
    """
    state = load_state()
    if not state or not state.get("phases"):
        event("phase_end.no_active_phase")
        return 2

    phases = state["phases"]
    current = phases[-1]
    if current["phase"] != args.phase:
        event(
            "phase_end.phase_mismatch",
            requested=args.phase,
            active=current["phase"],
        )
        return 2
    current["status"] = args.status
    current["ended"] = utc_now()
    current["commits"] = args.commits.split(",") if args.commits else []

    if (
        args.status == "success"
        and state.get("current_phase", 0) >= state.get("total_phases", 0)
    ):
        state["status"] = "success"
    elif args.status in ("failed", "pivot-needed"):
        state["status"] = args.status

    save_state(state)
    print(json.dumps({"ok": True, "phase": args.phase, "status": args.status}, indent=2))
    return 0


def cmd_pivot_check(args: argparse.Namespace) -> int:
    """Bump the repeat counter for ``finding_hash`` within a phase bucket.

    Args:
        args: parsed CLI namespace; expects ``phase`` (int) and ``finding_hash``.

    Returns:
        0 normally, 1 once a finding has been observed three or more times
        (PM should pivot). Also flips state status to ``pivot-needed`` then.
    """
    state = load_state()
    if not state:
        return 0

    bucket = state.setdefault("pivot_detector", {}).setdefault(f"phase-{args.phase}", {})
    bucket[args.finding_hash] = bucket.get(args.finding_hash, 0) + 1
    save_state(state)

    count = bucket[args.finding_hash]
    print(json.dumps({"finding_hash": args.finding_hash, "count": count}))
    if count >= 3:
        event("pivot.needed", reason="finding_repeated_3_rounds")
        state["status"] = "pivot-needed"
        save_state(state)
        return 1
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    """Print the current state as JSON, or a hint if no run is initialized.

    Returns:
        Always 0 — status queries do not fail.
    """
    state = load_state()
    if not state:
        print("auto-pilot: not initialized")
        return 0
    print(json.dumps(state, indent=2))
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    """Mark the run as stopped (terminal), recording ``stopped_at``.

    Returns:
        Always 0; a missing state file is treated as a no-op success.
    """
    state = load_state()
    if not state:
        print("auto-pilot: nothing to stop")
        return 0
    state["status"] = "stopped"
    state["stopped_at"] = utc_now()
    save_state(state)
    print(json.dumps({"ok": True, "status": "stopped"}, indent=2))
    return 0


_PHASE_HEADING = re.compile(r"^#{1,3}\s+Phase\b")


def _count_phases(spec_path: Path) -> int:
    """Count ``# Phase``, ``## Phase``, ``### Phase`` headings outside code fences.

    Skips lines inside ```` ``` ```` or ``~~~`` fenced blocks so example markdown
    embedded in the spec does not inflate the count. Floors at 1 so the loop
    always has work.

    Args:
        spec_path: path to the spec file.

    Returns:
        Number of phase headings (>= 1).
    """
    text = spec_path.read_text()
    count = 0
    in_fence = False
    fence_marker: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        if _PHASE_HEADING.match(stripped):
            count += 1
    return max(count, 1)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — parse ``argv`` and dispatch to the chosen subcommand.

    Args:
        argv: optional argv list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code from the dispatched subcommand handler.
    """
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
    rc: int = args.func(args)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
