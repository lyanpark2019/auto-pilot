"""Crash-recovery helpers for the auto-pilot loop.

Wires WorktreeManager.reap_orphans (leftover worktrees from aborted workers)
and _clear_stale_am_state (leftover git-am state from a kill-mid-apply) into
a production path.  Called once at headless-loop startup and exposed as
``orchestrator.py recover``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _log import event
from _state import STATE_DIR
from _worktree import StaleAmStateError, WorktreeManager


def run_recovery(
    *,
    repo_root: Path,
    state_dir: Path,
    max_age_hours: int = 24,
) -> dict[str, Any]:
    """Clear stale git-am state and reap aged orphan worktrees.

    Args:
        repo_root: root of the git repository (Path.cwd() in production).
        state_dir: base directory for auto-pilot state (contains contracts/ and
            worktrees/ subdirs).
        max_age_hours: worktrees whose sentinel is older than this are reaped.

    Returns:
        Dict with keys:
          - ``reaped``: list of reaped worktree path strings.
          - ``stale_am_cleared``: True when a leftover rebase-apply dir was
            found and cleared.
          - ``stale_am_error``: error message string if the abort failed, else None.
    """
    mgr = WorktreeManager(
        repo_root=repo_root,
        worktree_base=state_dir / "worktrees",
    )

    rebase_apply = repo_root / ".git" / "rebase-apply"
    had_stale_am = rebase_apply.exists()
    stale_am_cleared = False
    stale_am_error: str | None = None

    if had_stale_am:
        try:
            mgr._clear_stale_am_state()
            stale_am_cleared = not rebase_apply.exists()
        except StaleAmStateError as exc:
            stale_am_cleared = False
            stale_am_error = str(exc)

    reaped = mgr.reap_orphans(state_dir=state_dir, max_age_hours=max_age_hours)
    event("recover.done", reaped=len(reaped), stale_am_cleared=stale_am_cleared)

    return {
        "reaped": [str(p) for p in reaped],
        "stale_am_cleared": stale_am_cleared,
        "stale_am_error": stale_am_error,
    }


def cmd_recover(args: Any) -> int:
    """CLI handler for ``orchestrator.py recover``."""
    repo_root = Path.cwd()
    state_dir = Path(args.state_dir) if args.state_dir else STATE_DIR
    result = run_recovery(
        repo_root=repo_root,
        state_dir=state_dir,
        max_age_hours=args.max_age_hours,
    )
    print(json.dumps(result, indent=2))
    return 0


def register_cli_subparsers(sub: Any) -> None:
    """Register the ``recover`` subparser onto ``sub``."""
    p = sub.add_parser("recover")
    p.add_argument("--max-age-hours", type=int, default=24)
    p.add_argument("--state-dir", default=None)
    p.set_defaults(func=cmd_recover)
