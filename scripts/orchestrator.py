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
    python orchestrator.py review-status
    python orchestrator.py ledger-append | ledger-rebalance [--apply] [--project-root PATH]
    python orchestrator.py resume | discover (--check|--record) --graphify-version V [--scope-files a,b] | recover ... | improvements-list | improvements-gate | improvements-set-state | improvements-mirror ...
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
from _escalation_emit import emit_escalation
from _log import event
from _state import (
    STATE_DIR,
    PhaseEntry,
    State,
    load_state,
    state_transaction,
    utc_now,
)


def _emit(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _warn(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def _emit_json(payload: Any, *, indent: int | None = None) -> None:
    _emit(json.dumps(payload, indent=indent))


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a new auto-pilot run; 0 on success, 2 on missing spec or active run."""
    spec_path = Path(args.spec)
    if not spec_path.exists():
        event("init.spec_missing", path=spec_path)
        return 2

    # _count_phases does not need the lock — read-only spec scan.
    total_phases = _count_phases(spec_path)

    fresh: State = {
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
    with state_transaction() as txn:
        if txn.state.get("status") == "running" and not args.force:
            event("init.already_running", hint="pass --force to wipe or run stop first")
            return 2
        s: dict[str, Any] = txn.state  # type: ignore[assignment]
        s.clear()
        s.update(fresh)
        txn.commit()
    _emit_json({"ok": True, "state": fresh}, indent=2)
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
    with state_transaction() as txn:
        state = txn.state
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
            txn.commit()
            _emit_json({"ok": True, "phase": args.phase, "round": existing["round"]}, indent=2)
            return 0

        state["current_phase"] = args.phase
        phases.append(_new_phase_entry(args.phase, args.contracts))
        txn.commit()
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
    with state_transaction() as txn:
        state = txn.state
        if not state or not state.get("phases"):
            event("phase_end.no_active_phase")
            return 2

        current = _active_phase(state)
        if current is None or current["phase"] != args.phase:
            event("phase_end.phase_mismatch", requested=args.phase, active=current["phase"] if current else None)
            return 2

        approved_count = 0
        if args.status == "success" and os.environ.get("AUTO_PILOT_SKIP_EVIDENCE") != "1":
            # AUTO_PILOT_SKIP_EVIDENCE=1 bypasses the evidence gate — UNIT TESTS ONLY
            # (tests fabricate state without a real contracts tree). Never set in prod.
            result = _evidence.gate_phase_end(STATE_DIR / "contracts")
            if isinstance(result, tuple):
                suffix, message = result
                _warn(message)
                event(f"phase_end.{suffix}", phase=args.phase)
                emit_escalation(
                    problem_class="contract-schema-gap",
                    suggested_enrich_query=f"fix evidence chain: {message[:80]}",
                    approach="review-evidence-chain",
                    outcome="evidence_failed",
                    run_id=str(state.get("run_id", "")),
                    snippet=message,
                    repo_root=Path("."),
                    now=datetime.now(timezone.utc),
                )
                return 2  # critical: failed gate must not persist state
            approved_count = result
            expected = current.get("contracts")
            if expected is not None and approved_count != expected:
                _warn(
                    f"BLOCKED phase-end --status success: evidence-approved count "
                    f"{approved_count} != expected contract count {expected}"
                )
                event("phase_end.approved_count_mismatch", phase=args.phase,
                      approved=approved_count, expected=expected)
                return 2  # critical: incomplete phase must not advance state

        # Auto-append ledger records — telemetry; runs inside state lock so the
        # ledger append_phase_records acquires the separate LEDGER lock.
        # State→ledger order is consistent across callers; no deadlock possible.
        try:
            import _ledger  # noqa: PLC0415
            _ledger.append_phase_records(Path.cwd(), STATE_DIR / "contracts")
        except Exception as exc:  # noqa: BLE001
            _warn(f"ledger auto-append failed (telemetry, non-blocking): {exc}")
        current["approved"] = approved_count
        _close_phase(current, args.status, args.commits)
        _update_run_status(state, args.status)
        txn.commit()
        _emit_json({"ok": True, "phase": args.phase, "status": args.status}, indent=2)
        return 0


def cmd_resume(_: argparse.Namespace) -> int:
    """Clear ``cost-cap`` → ``running``; other statuses are untouched (return 1)."""
    with state_transaction() as txn:
        state = txn.state
        if state.get("status") != "cost-cap":
            _warn(f"resume clears cost-cap only; status={state.get('status')!r}")
            return 1
        state["status"] = "running"
        txn.commit()
        event("orchestrator.resume_after_cap",
              cost_usd=state.get("cost_usd"), tokens=state.get("tokens"))
        return 0


def cmd_pivot_check(args: argparse.Namespace) -> int:
    """Bump repeat counter for ``finding_hash``; return 1 (+ pivot-needed) at 3rd hit."""
    run_id = ""
    with state_transaction() as txn:
        state = txn.state
        if not state:
            return 0
        run_id = str(state.get("run_id", ""))
        bucket = state.setdefault("pivot_detector", {}).setdefault(f"phase-{args.phase}", {})
        bucket[args.finding_hash] = bucket.get(args.finding_hash, 0) + 1
        count = bucket[args.finding_hash]
        if count >= 3:
            state["status"] = "pivot-needed"
        txn.commit()
    _emit_json({"finding_hash": args.finding_hash, "count": count})
    if count >= 3:
        event("pivot.needed", reason="finding_repeated_3_rounds")
        emit_escalation(
            problem_class="doom-loop",
            suggested_enrich_query=f"break repeated failure: {args.finding_hash}",
            approach="deterministic-retry",
            outcome="repeated-3-rounds",
            run_id=run_id,
            snippet=f"phase-{args.phase} finding {args.finding_hash} x{count}",
            repo_root=Path("."),
            now=datetime.now(timezone.utc),
        )
        return 1
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    """Print current state as JSON, or a hint when uninitialised. Always 0."""
    state = load_state()
    if not state:
        _emit("auto-pilot: not initialized")
        return 0
    _emit_json(state, indent=2)
    return 0


def cmd_stop(_: argparse.Namespace) -> int:
    """Mark the run as stopped (terminal), recording ``stopped_at``. Always returns 0."""
    with state_transaction() as txn:
        state = txn.state
        if not state:
            _emit("auto-pilot: nothing to stop")
            return 0
        state["status"] = "stopped"
        state["stopped_at"] = utc_now()
        txn.commit()
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
    import _contract_check
    return _contract_check.build_artifact(contract_path)


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

    import _contract_check
    try:
        artifact = _dispatch_contract_artifact(contract_path)
    except _contract_check.ContractCheckError as exc:
        event("dispatch_contract_check.invalid", error=str(exc), error_type="ContractCheckError")
        _emit_json({"ok": False, "error": str(exc)}, indent=2)
        return 1
    artifact_path = _write_dispatch_artifact(contract_path, artifact)
    event("dispatch_contract_check.ok", sha=artifact["contract_sha256"][:16], artifact=str(artifact_path))
    _emit_json({"ok": True, "artifact": str(artifact_path), **artifact}, indent=2)
    return 0



def cmd_review_status(_: argparse.Namespace) -> int:
    """Print the reviewer heartbeat table for the active phase (§4 PM visibility)."""
    import _heartbeat
    _emit(_heartbeat.render_table(STATE_DIR / "contracts"))
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


def cmd_ledger_append(args: argparse.Namespace) -> int:
    """Auto-append phase-end ledger records for finished contracts (telemetry)."""
    import _ledger  # noqa: PLC0415
    project_root = Path(args.project_root) if args.project_root else Path.cwd()
    # F-C: STATE_DIR is relative — append directly so --project-root works.
    contracts_root = project_root / STATE_DIR / "contracts" if not STATE_DIR.is_absolute() else STATE_DIR / "contracts"
    try:
        count = _ledger.append_phase_records(project_root, contracts_root)
    except Exception as exc:  # noqa: BLE001
        _warn(f"ledger-append: {exc}")
        return 1
    _emit(f"ledger: appended {count} record(s)")
    return 0


def _print_rebalance_proposals(proposals: list[dict[str, Any]]) -> None:
    _emit(f"{'role':<24} {'task_class':<20} {'rule':<28} {'from':<12} {'to':<12} evidence")
    for p in proposals:
        ev = ",".join(p.get("evidence") or [])
        _emit(
            f"{p.get('role',''):<24} {p.get('task_class',''):<20} "
            f"{p.get('rule',''):<28} {p.get('from_model',''):<12} "
            f"{p.get('to_model',''):<12} {ev}"
        )


def _apply_rebalance(ledger: dict[str, Any], proposals: list[dict[str, Any]]) -> None:
    rebalance_log = ledger.setdefault("rebalance_log", [])
    assignments = ledger.setdefault("assignments", {})
    for p in proposals:
        rebalance_log.append(p)
        role = p.get("role", "")
        task_class = p.get("task_class", "")
        to_model = p.get("to_model", "")
        if role and to_model:
            # F9: key by composite "<role>/<task_class>" so different task
            # classes within the same role get independent assignments.
            comp_key = f"{role}/{task_class}" if task_class else role
            assignments.setdefault(comp_key, {})["model"] = to_model


def cmd_ledger_rebalance(args: argparse.Namespace) -> int:
    """Evaluate (and optionally apply) model rebalance proposals."""
    import _ledger  # noqa: PLC0415
    import _routing  # noqa: PLC0415
    project_root = Path(args.project_root) if args.project_root else Path.cwd()
    ledger_path = project_root / ".claude" / "routing" / "ledger.yaml"
    try:
        ladder = _routing.tier_ladder()
    except _routing.RoutingConfigError as exc:
        _warn(f"ledger-rebalance: {exc}")
        return 2

    if args.apply:
        # commit() saves in ledger_transaction.__exit__ → save errors surface on
        # `with` exit; outer except keeps the pre-refactor "save fail → rc 2".
        try:
            with _ledger.ledger_transaction(ledger_path) as txn:
                ledger = txn.ledger
                try:
                    _ledger.validate_ledger(ledger)
                except _ledger.LedgerError as exc:
                    _warn(f"ledger-rebalance: {exc}")
                    return 2
                proposals = _ledger.evaluate_rebalance(ledger, ladder)
                if not proposals:
                    _emit("ledger-rebalance: no proposals")
                    return 0
                _print_rebalance_proposals(proposals)
                _apply_rebalance(ledger, proposals)
                txn.commit()
        except (_ledger.LedgerError, OSError) as exc:
            _warn(f"ledger-rebalance --apply save failed: {exc}")
            return 2
        _emit(f"ledger-rebalance: applied {len(proposals)} proposal(s)")
        return 0

    # Dry-run: read-only, no lock needed.
    try:
        ledger = _ledger.load_ledger(ledger_path)
        # F11: validate before evaluating — catches schema drift early.
        _ledger.validate_ledger(ledger)
    except _ledger.LedgerError as exc:
        _warn(f"ledger-rebalance: {exc}")
        return 2
    proposals = _ledger.evaluate_rebalance(ledger, ladder)
    if not proposals:
        _emit("ledger-rebalance: no proposals")
        return 0
    _print_rebalance_proposals(proposals)
    return 0


_PHASE_HEADING = re.compile(r"^#{1,3}\s+Phase\b")


def _count_phases(spec_path: Path) -> int:
    """Count Phase headings outside code fences; floors at 1."""
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
    sub.add_parser("resume").set_defaults(func=cmd_resume)
    sub.add_parser("review-status").set_defaults(func=cmd_review_status)

    p_dcc = sub.add_parser("dispatch-contract-check")
    p_dcc.add_argument("--contract", required=True)
    p_dcc.set_defaults(func=cmd_dispatch_contract_check)

    p_disc = sub.add_parser("discover")
    disc_mode = p_disc.add_mutually_exclusive_group(required=True)
    disc_mode.add_argument("--check", action="store_true")
    disc_mode.add_argument("--record", action="store_true")
    p_disc.add_argument("--graphify-version", required=True)
    p_disc.add_argument("--scope-files", default="",
                        help="comma-separated; trailing-slash entries match as dir prefixes")
    p_disc.set_defaults(func=cmd_discover)

    p_la = sub.add_parser("ledger-append")
    p_la.add_argument("--project-root", default=None)
    p_la.set_defaults(func=cmd_ledger_append)

    p_lr = sub.add_parser("ledger-rebalance")
    p_lr.add_argument("--apply", action="store_true")
    p_lr.add_argument("--project-root", default=None)
    p_lr.set_defaults(func=cmd_ledger_rebalance)

    import _promotion  # noqa: PLC0415
    _promotion.register_cli_subparsers(sub)
    import _recover  # noqa: PLC0415
    _recover.register_cli_subparsers(sub)
    import _round_budget  # noqa: PLC0415
    _round_budget.register_cli_subparsers(sub)
    import _mirror_learnings  # noqa: PLC0415
    _mirror_learnings.register_cli_subparsers(sub)
    import measure_learnings_injection  # noqa: PLC0415
    measure_learnings_injection.register_cli_subparsers(sub)
    import _enrich_persist  # noqa: PLC0415
    _enrich_persist.register_cli_subparsers(sub)
    import measure_enrich_precision  # noqa: PLC0415
    measure_enrich_precision.register_cli_subparsers(sub)
    import _escalation  # noqa: PLC0415
    _escalation.register_cli_subparsers(sub)
    import measure_escalation  # noqa: PLC0415
    measure_escalation.register_cli_subparsers(sub)
    import _escalation_seed  # noqa: PLC0415
    _escalation_seed.register_cli_subparsers(sub)
    import _resolve_learnings_cli  # noqa: PLC0415
    _resolve_learnings_cli.register_cli_subparsers(sub)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — parse ``argv`` and dispatch to the chosen subcommand."""
    args = _build_cli_parser().parse_args(argv)
    rc: int = args.func(args)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
