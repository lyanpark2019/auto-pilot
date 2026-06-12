#!/usr/bin/env python3
"""auto-pilot orchestrator helper.

The actual PM loop runs in the Claude Code main session (operator-selected model) — this file
is a state-management and reporting helper invoked by the skill/command. It does
NOT itself dispatch agents (only the main session can call the Agent tool).

Usage:
    python orchestrator.py init  --spec docs/specs/X.md --max-workers 10
    python orchestrator.py phase-start  --phase 1 --contracts 6
    python orchestrator.py phase-end    --phase 1 --status success --commits sha1,sha2
    python orchestrator.py pivot-check  --phase 1 --finding-hash abc123
    python orchestrator.py status
    python orchestrator.py stop
    python orchestrator.py dispatch-contract-check --contract <path>
    python orchestrator.py round-budget --score-dir .planning/score --round N
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _evidence
from _log import event
from _state import (
    STATE_DIR,
    PhaseEntry,
    State,
    load_state,
    save_state,
    utc_now,
)


def _emit(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _warn(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def _emit_json(payload: Any, *, indent: int | None = None) -> None:
    _emit(json.dumps(payload, indent=indent))


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
    _emit_json({"ok": True, "state": state}, indent=2)
    return 0


def _ensure_run_id(state: State) -> None:
    if "run_id" not in state or not state.get("run_id"):
        import uuid
        state["run_id"] = uuid.uuid4().hex


def _phase_entry(phases: list[PhaseEntry], phase: int) -> PhaseEntry | None:
    return next((p for p in phases if p["phase"] == phase), None)


def _restart_phase(state: State, existing: PhaseEntry, phase: int, contracts: int) -> None:
    existing["round"] = existing["round"] + 1
    existing["status"] = "running"
    existing["ended"] = None
    existing["contracts"] = contracts
    state["current_phase"] = phase


def _new_phase_entry(phase: int, contracts: int) -> PhaseEntry:
    return {
        "phase": phase,
        "status": "running",
        "round": 1,
        "contracts": contracts,
        "approved": 0,
        "started": utc_now(),
        "ended": None,
        "commits": [],
    }


def cmd_phase_start(args: argparse.Namespace) -> int:
    """Begin (or retry) a phase, validating bounds and bumping ``round`` on retry."""
    state = load_state()
    if not state:
        event("phase_start.no_state")
        return 2

    _ensure_run_id(state)
    total = state.get("total_phases", 0)
    if args.phase < 1 or args.phase > total:
        event("phase_start.out_of_range", phase=args.phase, total_phases=total)
        return 2

    phases: list[PhaseEntry] = state.setdefault("phases", [])
    existing = _phase_entry(phases, args.phase)
    if existing is not None:
        if existing["status"] == "running":
            event("phase_start.already_running", phase=args.phase)
            return 2
        _restart_phase(state, existing, args.phase, args.contracts)
        save_state(state)
        _emit_json({"ok": True, "phase": args.phase, "round": existing["round"]}, indent=2)
        return 0

    state["current_phase"] = args.phase
    phases.append(_new_phase_entry(args.phase, args.contracts))
    save_state(state)
    _emit_json({"ok": True, "phase": args.phase}, indent=2)
    return 0


def _active_phase(state: State) -> PhaseEntry | None:
    phases = state.get("phases")
    return phases[-1] if phases else None


def _close_phase(current: PhaseEntry, status: str, commits: str) -> None:
    current["status"] = status
    current["ended"] = utc_now()
    current["commits"] = commits.split(",") if commits else []


def _update_run_status(state: State, status: str) -> None:
    if status == "success" and state.get("current_phase", 0) >= state.get("total_phases", 0):
        state["status"] = "success"
    elif status in ("failed", "pivot-needed"):
        state["status"] = status


def cmd_phase_end(args: argparse.Namespace) -> int:
    """Close out the active phase with a final status and commit list.

    On --status success, refuses (exit 2, no state write) unless the active
    phase's evidence chain is complete (see _evidence.gate_phase_end).
    AUTO_PILOT_SKIP_EVIDENCE=1 bypasses the gate — unit tests only, never prod.
    """
    state = load_state()
    if not state or not state.get("phases"):
        event("phase_end.no_active_phase")
        return 2

    current = _active_phase(state)
    if current is None or current["phase"] != args.phase:
        event("phase_end.phase_mismatch", requested=args.phase, active=current["phase"] if current else None)
        return 2

    if args.status == "success" and os.environ.get("AUTO_PILOT_SKIP_EVIDENCE") != "1":
        # AUTO_PILOT_SKIP_EVIDENCE=1 bypasses the evidence gate — UNIT TESTS ONLY
        # (tests fabricate state without a real contracts tree). Never set in prod.
        blocked = _evidence.gate_phase_end(STATE_DIR / "contracts")
        if blocked is not None:
            suffix, message = blocked
            _warn(message)
            event(f"phase_end.{suffix}", phase=args.phase)
            return 2

    _close_phase(current, args.status, args.commits)
    _update_run_status(state, args.status)
    save_state(state)
    _emit_json({"ok": True, "phase": args.phase, "status": args.status}, indent=2)
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
    _emit_json({"finding_hash": args.finding_hash, "count": count})
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
        _emit("auto-pilot: not initialized")
        return 0
    _emit_json(state, indent=2)
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    """Mark the run as stopped (terminal), recording ``stopped_at``.

    Returns:
        Always 0; a missing state file is treated as a no-op success.
    """
    state = load_state()
    if not state:
        _emit("auto-pilot: nothing to stop")
        return 0
    state["status"] = "stopped"
    state["stopped_at"] = utc_now()
    save_state(state)
    _emit_json({"ok": True, "status": "stopped"}, indent=2)
    return 0


def _validate_contract_for_dispatch(contract_path: Path) -> tuple[bool, str]:
    import _contract

    try:
        _contract.validate(json.loads(contract_path.read_text()))
    except _contract.ContractValidationError as exc:
        return False, str(exc)
    return True, ""


def _dispatch_contract_artifact(contract_path: Path) -> dict[str, Any]:
    import hashlib

    contract_bytes = contract_path.read_bytes()
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()
    return {
        "contract_sha256": contract_sha,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": json.loads(contract_bytes.decode()).get("schema_version", 1),
        "result": "pass",
    }


def _write_dispatch_artifact(contract_path: Path, artifact: dict[str, Any]) -> Path:
    artifact_path = contract_path.parent / "contract-check.json"
    artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return artifact_path


def cmd_dispatch_contract_check(args: argparse.Namespace) -> int:
    """Validate a contract file and write a pass artifact beside it."""
    contract_path = Path(args.contract)
    if not contract_path.exists():
        event("dispatch_contract_check.missing", path=str(contract_path))
        return 2

    ok, error = _validate_contract_for_dispatch(contract_path)
    if not ok:
        event("dispatch_contract_check.invalid", error=error, error_type="ContractValidationError")
        _emit_json({"ok": False, "error": error}, indent=2)
        return 1

    artifact = _dispatch_contract_artifact(contract_path)
    artifact_path = _write_dispatch_artifact(contract_path, artifact)
    event("dispatch_contract_check.ok", sha=artifact["contract_sha256"][:16], artifact=str(artifact_path))
    _emit_json({"ok": True, "artifact": str(artifact_path), **artifact}, indent=2)
    return 0


def _load_findings(score_dir: Path, r: int) -> dict[str, Any]:
    """Load a findings-round-N.json file; return {} and log if missing."""
    p = score_dir / f"findings-round-{r}.json"
    if not p.exists():
        event("round_budget.missing_file", path=str(p))
        return {}
    parsed: dict[str, Any] = json.loads(p.read_text())
    return parsed


def _count_findings(data: dict[str, Any]) -> int:
    """Sum reviewer finding counts from a findings file payload."""
    reviewers: dict[str, Any] = data.get("reviewers", {})
    return sum(int(v.get("count", 0)) for v in reviewers.values())


def _emit_hard_stop(n: int, c_prev: int, c_curr: int) -> int:
    """Print HARD-STOP verdict to stdout+stderr and return exit 3."""
    msg = "HARD-STOP: 전략 전환 필요"
    _emit_json({
        "round": n, "count_prev": c_prev, "count_curr": c_curr, "verdict": msg,
    }, indent=2)
    _warn(msg)
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
        data_n = _load_findings(score_dir, n)
        if not data_n:
            return 2
        c = _count_findings(data_n)
        _emit_json({"round": n, "count": c, "status": "informational"}, indent=2)
        return 0
    data_prev = _load_findings(score_dir, n - 1)
    data_curr = _load_findings(score_dir, n)
    if not data_prev or not data_curr:
        return 2
    c_prev = _count_findings(data_prev)
    c_curr = _count_findings(data_curr)
    if c_curr >= c_prev:
        return _emit_hard_stop(n, c_prev, c_curr)
    _emit_json({
        "round": n, "count_prev": c_prev, "count_curr": c_curr,
        "verdict": "round 4 = final cap",
    }, indent=2)
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    """Graphify-context discovery seam: record provenance or check freshness.

    ``--record`` exits 0; ``--check`` exits 0 when fresh, 1 when stale.
    """
    import _discovery

    repo_root = Path.cwd()
    if args.record:
        payload = _discovery.record_provenance(
            repo_root=repo_root, state_dir=STATE_DIR,
            graphify_version=args.graphify_version,
        )
        event("discover.recorded", build_commit=payload["build_commit"][:8],
              graphify_version=args.graphify_version)
        _emit_json({"ok": True, **payload}, indent=2)
        return 0

    scope = tuple(s.strip() for s in args.scope_files.split(",") if s.strip())
    verdict = _discovery.check_freshness(
        repo_root=repo_root, state_dir=STATE_DIR,
        graphify_version=args.graphify_version, scope_files=scope,
    )
    event("discover.checked", fresh=verdict.fresh, reason=verdict.reason)
    _emit_json(verdict.to_json(), indent=2)
    return 0 if verdict.fresh else 1


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


def _build_cli_parser() -> argparse.ArgumentParser:
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

    p_dcc = sub.add_parser("dispatch-contract-check")
    p_dcc.add_argument("--contract", required=True)
    p_dcc.set_defaults(func=cmd_dispatch_contract_check)

    p_rb = sub.add_parser("round-budget")
    p_rb.add_argument("--score-dir", required=True)
    p_rb.add_argument("--round", type=int, required=True)
    p_rb.set_defaults(func=cmd_round_budget)

    p_disc = sub.add_parser("discover")
    disc_mode = p_disc.add_mutually_exclusive_group(required=True)
    disc_mode.add_argument("--check", action="store_true")
    disc_mode.add_argument("--record", action="store_true")
    p_disc.add_argument("--graphify-version", required=True)
    p_disc.add_argument("--scope-files", default="",
                        help="comma-separated; trailing-slash entries match as dir prefixes")
    p_disc.set_defaults(func=cmd_discover)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — parse ``argv`` and dispatch to the chosen subcommand."""
    args = _build_cli_parser().parse_args(argv)
    rc: int = args.func(args)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
