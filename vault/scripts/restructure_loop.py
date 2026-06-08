#!/usr/bin/env python3
# ruff: noqa: E402
"""Autonomous Obsidian restructure loop.

Runs phases 1-7 in order. Idempotent + resume-safe via state file at
~/.claude/state/obsidian-restructure-state.json.

Usage:
    python3 restructure_loop.py [--dry-run] [--phase N] [--reset]
                                 [--obsidian PATH] [--project PATH]
                                 [--state PATH]

Each phase:
  - dry_run() — describe planned ops, no side effects
  - run()     — execute, return PhaseResult (completed | partial | failed)
  - verify()  — post-run sanity check
  - rollback() — best-effort revert (Phase 1 backups are the real safety net)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.restructure_phases._base import PhaseContext, PhaseResult
from scripts.restructure_phases import _state
from scripts.restructure_phases.phase01_backup import BackupPhase
from scripts.restructure_phases.phase02_rename import RenameSimplePhase
from scripts.restructure_phases.phase03_sportic365_merge import Sportic365MergePhase
from scripts.restructure_phases.phase04_notebooklm_split import NotebookLMSplitPhase
from scripts.restructure_phases.phase05_skeletons import NewVaultSkeletonsPhase
from scripts.restructure_phases.phase06_vault_build import VaultBuildPerDomainPhase
from scripts.restructure_phases.phase07_notebooklm_create import NotebookLMCreatePhase
from scripts.restructure_phases.phase08_cleanup import CleanupPhase

PHASES = [
    BackupPhase,
    RenameSimplePhase,
    Sportic365MergePhase,
    NotebookLMSplitPhase,
    NewVaultSkeletonsPhase,
    VaultBuildPerDomainPhase,
    NotebookLMCreatePhase,
    CleanupPhase,
]

MAX_RETRIES = 3


def make_ctx(args: Any) -> PhaseContext:
    obsidian = Path(args.obsidian).expanduser().resolve()
    project = Path(args.project).expanduser().resolve()
    state_path = Path(args.state).expanduser().resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(args.backup_dir).expanduser().resolve()
    return PhaseContext(
        obsidian_root=obsidian,
        project_root=project,
        plugin_root=PLUGIN_ROOT,
        state_path=state_path,
        backup_dir=backup_dir,
        dry_run_mode=args.dry_run,
        execute_builds=args.execute_builds,
        only_domain=args.only_domain,
    )


def _phase_already_done(phase: Any, state: dict[str, Any], force: bool) -> bool:
    p_state = state["phases"].setdefault(phase.name, {"status": "pending"})
    if p_state.get("status") != "completed" or force:
        return False
    phase.ctx.trace(f"--- {phase.name}: already completed (skip) ---")
    return True


def _run_dry_phase(phase: Any, ctx: PhaseContext, state: dict[str, Any]) -> bool:
    ctx.trace(phase.dry_run())
    _state.mark_phase(state, phase.name, "dry_run_simulated")
    _state.save(ctx.state_path, state)
    return True


PHASE_FAILURES = (OSError, RuntimeError, ValueError, TypeError)


def _execute_phase_attempt(phase: Any) -> PhaseResult:
    try:
        return phase.run()
    except PHASE_FAILURES as e:
        return PhaseResult(status="failed", detail=f"exception: {e!r}")


def _rollback_phase(phase: Any, ctx: PhaseContext) -> None:
    try:
        phase.rollback()
    except PHASE_FAILURES as e:
        ctx.trace(f"  rollback raised: {e!r}")


def _accept_result(phase: Any, ctx: PhaseContext, state: dict[str, Any], result: PhaseResult) -> bool:
    if result.status not in ("completed", "partial"):
        return False
    ok, why = phase.verify()
    if ok:
        _state.mark_phase(state, phase.name, result.status, detail=result.detail, **result.artifacts)
        _state.save(ctx.state_path, state)
        ctx.trace(f"  → {result.status} ({result.detail})")
        return True
    ctx.trace(f"  verify failed: {why}")
    _state.append_error(state, phase.name, f"verify failed: {why}")
    return False


def run_one(phase_cls: type[Any], ctx: PhaseContext, state: dict[str, Any], force: bool = False) -> bool:
    """Returns True if phase completed (or was already done)."""
    phase = phase_cls(ctx)
    if _phase_already_done(phase, state, force):
        return True
    ctx.trace(f"=== {phase.name} ===")
    if ctx.dry_run_mode:
        return _run_dry_phase(phase, ctx, state)
    for attempt in range(1, MAX_RETRIES + 1):
        ctx.trace(f"  attempt {attempt}/{MAX_RETRIES}")
        result = _execute_phase_attempt(phase)
        if _accept_result(phase, ctx, state, result):
            return True
        ctx.trace(f"  failed: {result.detail}")
        _state.append_error(state, phase.name, f"attempt {attempt}: {result.detail}")
        if attempt < MAX_RETRIES:
            _rollback_phase(phase, ctx)
    _state.mark_phase(state, phase.name, "failed")
    _state.save(ctx.state_path, state)
    return False


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Autonomous Obsidian restructure loop")
    ap.add_argument("--dry-run", action="store_true", help="Simulate all phases")
    ap.add_argument("--phase", type=int, default=None, help="Start from phase N (1-7)")
    ap.add_argument("--reset", action="store_true", help="Reset state before run")
    ap.add_argument("--obsidian", default="~/Documents/Obsidian", help="Obsidian root")
    ap.add_argument("--project", default="~/Documents/Project", help="Project root")
    ap.add_argument("--state", default="~/.claude/state/obsidian-restructure-state.json", help="State file path")
    ap.add_argument("--backup-dir", default="/tmp/obsidian-backups", help="Backup tarball dir")
    ap.add_argument("--verify-all", action="store_true", help="Re-verify every phase, mark stale ones pending")
    ap.add_argument("--execute-builds", action="store_true", help="Phase 6: actually shell-out to `claude -p /vault-build` per domain")
    ap.add_argument("--only-domain", default=None, help="Phase 6: restrict execution to a single domain (e.g. ga4-collector)")
    return ap


def _reset_state_if_requested(ctx: PhaseContext, reset: bool) -> None:
    if reset and ctx.state_path.exists():
        backup = ctx.state_path.with_suffix(f".reset-{int(time.time())}.json")
        ctx.state_path.rename(backup)
        ctx.trace(f"state reset; old → {backup}")


def _verify_all_phases(ctx: PhaseContext, state: dict[str, Any]) -> None:
    ctx.trace("=== verify-all: re-running verifiers, marking stale ===")
    for phase_cls in PHASES:
        phase = phase_cls(ctx)
        ok, why = phase.verify()
        if not ok:
            ctx.trace(f"  {phase.name}: stale ({why}) — marking pending")
            state["phases"][phase.name]["status"] = "pending"
        else:
            ctx.trace(f"  {phase.name}: ok ({why})")
    _state.save(ctx.state_path, state)


def _run_phase_sequence(ctx: PhaseContext, state: dict[str, Any], start_idx: int) -> list[str]:
    failures: list[str] = []
    for i, phase_cls in enumerate(PHASES[start_idx:], start=start_idx + 1):
        ok = run_one(phase_cls, ctx, state)
        if not ok:
            failures.append(phase_cls.name)
            ctx.trace(f"!! halting at {phase_cls.name} (deps unmet for downstream)")
            break
        state["current_phase"] = i
        _state.save(ctx.state_path, state)
    return failures


def _write_final_report(ctx: PhaseContext, state: dict[str, Any], failures: list[str], dry_run: bool) -> None:
    summary = {pc.name: state["phases"].get(pc.name, {}).get("status", "unknown") for pc in PHASES}
    ctx.trace("\n=== Final phase summary ===")
    for k, v in summary.items():
        ctx.trace(f"  {k}: {v}")

    report_path = ctx.state_path.parent / "obsidian-restructure-final-report.md"
    lines = ["# Obsidian Restructure Final Report", ""]
    lines.append(f"- Run mode: {'dry-run' if dry_run else 'live'}")
    lines.append(f"- Started: {state.get('started_at')}")
    lines.append(f"- Failures: {failures or 'none'}")
    lines.append("")
    lines.append("## Phase status")
    for k, v in summary.items():
        lines.append(f"- **{k}** — {v}")
    if state.get("errors"):
        lines.append("\n## Errors")
        for e in state["errors"][-20:]:
            lines.append(f"- [{e['ts']}] {e['phase']}: {e['msg']}")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    ctx.trace(f"\nreport → {report_path}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    ctx = make_ctx(args)
    _reset_state_if_requested(ctx, args.reset)
    state = _state.load(ctx.state_path)
    if args.verify_all:
        _verify_all_phases(ctx, state)
    start_idx = (args.phase - 1) if args.phase else 0
    failures = _run_phase_sequence(ctx, state, start_idx)
    _write_final_report(ctx, state, failures, args.dry_run)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
