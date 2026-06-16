"""CLI subcommand: orchestrator.py resolve-learnings.

Deterministic seam that converts the prose-only injection step (agents/pm-orchestrator.md
step 0b) into a verifiable CLI call.  ``measure-injection`` reports
``scope_addressable_pct=0.0`` when no Python call site invokes
``_learnings.resolve_learnings`` — this subcommand closes that gap so the PM
can invoke the injection step programmatically and measure it.

ADR 0002: injection reads the Hermes ledger, never vault prose.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def register_cli_subparsers(sub: Any) -> None:
    """Register ``resolve-learnings`` onto the orchestrator CLI sub-parser group."""
    p = sub.add_parser("resolve-learnings")
    p.add_argument(
        "--repo-root", default=".", dest="repo_root",
        help="project root (default: .); used to locate the Hermes ledger",
    )
    p.add_argument(
        "--scope", action="append", default=[], dest="scope_files", metavar="SCOPE",
        help=(
            "scope entry (repeatable; trailing '/' = dir prefix match). "
            "Mirrors contract scope_files convention."
        ),
    )
    p.add_argument(
        "--dest-dir", required=True, dest="dest_dir",
        help="contract bundle directory; learnings.md written to <dest-dir>/context-bundle/",
    )
    p.set_defaults(func=cmd_resolve_learnings)


def cmd_resolve_learnings(args: Any) -> int:
    """Resolve and write context-bundle/learnings.md; emit one JSON status line.

    Always returns 0 — a None result (no matching gate-passed tickets) means
    learnings-blind dispatch, never an error.  The caller (PM) checks
    ``matched`` to decide whether to thread the path into snapshot_context.
    """
    import _learnings  # noqa: PLC0415

    repo_root = Path(args.repo_root).resolve()
    scope_files: list[str] = list(args.scope_files)
    dest_dir = Path(args.dest_dir)

    try:
        result_path = _learnings.resolve_learnings(repo_root, scope_files, dest_dir)
    except OSError as exc:
        # I/O failure writing the bundle (e.g. a non-directory dest-dir parent) must
        # not crash dispatch — injection is additive, so degrade to learnings-blind.
        sys.stderr.write(f"resolve-learnings: I/O error, ran learnings-blind: {exc}\n")
        sys.stdout.write(
            json.dumps({"ok": False, "learnings_path": None, "matched": 0}) + "\n")
        return 0

    payload: dict[str, Any] = {
        "ok": True,
        "learnings_path": str(result_path) if result_path is not None else None,
        "matched": 1 if result_path is not None else 0,
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    return 0
