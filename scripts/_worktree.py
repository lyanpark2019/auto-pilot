"""Worktree lifecycle for auto-pilot workers.

Invariant: only $ROOT (main repo) calls these; worktrees are ephemeral.
All ops use `git -C <path>` — never relies on cwd.

Locking: apply_to_main holds .planning/auto-pilot/main-apply.lock (flock).
All mutations of $ROOT (not worktrees) MUST go through WorktreeManager.apply_to_main().
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class WorktreeHandle:
    path: Path
    branch: str
    base_sha: str
    contract_id: str
    created_at: str

    def write(self, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        d = asdict(self)
        d["path"] = str(self.path)
        target.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n")

    @classmethod
    def read(cls, source: Path) -> "WorktreeHandle":
        d = cast(dict[str, Any], json.loads(source.read_text()))
        d["path"] = Path(d["path"])
        return cls(**d)


# PatchResult algebraic data type
@dataclass(frozen=True)
class PatchResult:
    """Base class for patch collection outcomes."""


@dataclass(frozen=True)
class NoOp(PatchResult):
    """Worker produced no diff (empty change set)."""


@dataclass(frozen=True)
class NeedsRebase(PatchResult):
    """HEAD no longer descends from base_sha."""
    reason: str
    current_base: str


@dataclass(frozen=True)
class RejectMultipleCommits(PatchResult):
    """Worker produced more than one commit; one-commit invariant violated."""
    count: int


@dataclass(frozen=True)
class PatchSeries(PatchResult):
    """Worker produced exactly one commit; mbox ready for am."""
    mbox: Path
