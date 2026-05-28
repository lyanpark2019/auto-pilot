"""Worktree lifecycle for auto-pilot workers.

Invariant: only $ROOT (main repo) calls these; worktrees are ephemeral.
All ops use `git -C <path>` — never relies on cwd.

Locking: apply_to_main holds .planning/auto-pilot/main-apply.lock (flock).
All mutations of $ROOT (not worktrees) MUST go through WorktreeManager.apply_to_main().
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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


class InvalidBranchNameError(Exception):
    """Branch name fails `git check-ref-format`."""


class WorktreeManager:
    """Owns the lifecycle of git worktrees for auto-pilot workers."""

    def __init__(self, *, repo_root: Path, worktree_base: Path) -> None:
        self.repo_root = repo_root
        self.worktree_base = worktree_base

    def create(self, contract: dict[str, Any], *, contract_dir: Path) -> WorktreeHandle:
        """Create a worktree on the canonical branch derived from contract.id.

        1. Validate branch name via `git check-ref-format`.
        2. `git -C $ROOT worktree add <wt_path> -b <branch> <base_sha>`.
        3. Write `.auto-pilot-worktree` sentinel containing contract.id inside wt.
        4. Persist WorktreeHandle to `<contract_dir>/worktree-handle.json`.
        """
        contract_id = contract["id"]
        branch = f"auto-pilot/{contract_id}"
        refcheck = subprocess.run(
            ["git", "check-ref-format", f"refs/heads/{branch}"],
            capture_output=True, text=True,
        )
        if refcheck.returncode != 0:
            raise InvalidBranchNameError(f"{branch!r}: {refcheck.stderr.strip()}")

        wt_path = self.worktree_base / contract_id
        wt_path.parent.mkdir(parents=True, exist_ok=True)

        base_sha = contract["snapshot_shas"]["base_sha"]
        subprocess.run(
            ["git", "-C", str(self.repo_root), "worktree", "add",
             str(wt_path), "-b", branch, base_sha],
            check=True, capture_output=True,
        )
        (wt_path / ".auto-pilot-worktree").write_text(contract_id + "\n")

        handle = WorktreeHandle(
            path=wt_path,
            branch=branch,
            base_sha=base_sha,
            contract_id=contract_id,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        handle.write(contract_dir / "worktree-handle.json")
        return handle

    def collect_patches(self, handle: WorktreeHandle, *, contract_dir: Path) -> PatchResult:
        """Inspect worker's worktree HEAD vs base_sha; return one of NoOp,
        NeedsRebase, RejectMultipleCommits, PatchSeries."""
        ancestry = subprocess.run(
            ["git", "-C", str(handle.path), "merge-base", "--is-ancestor",
             handle.base_sha, "HEAD"],
            capture_output=True, text=True,
        )
        if ancestry.returncode != 0:
            try:
                cb = subprocess.check_output(
                    ["git", "-C", str(handle.path), "merge-base",
                     handle.base_sha, "HEAD"],
                    text=True,
                ).strip()
            except subprocess.CalledProcessError:
                cb = ""
            return NeedsRebase(reason="HEAD does not descend from base_sha",
                                current_base=cb)

        count_out = subprocess.check_output(
            ["git", "-C", str(handle.path), "rev-list", "--count",
             f"{handle.base_sha}..HEAD"],
            text=True,
        ).strip()
        n = int(count_out)
        if n == 0:
            return NoOp()
        if n != 1:
            return RejectMultipleCommits(count=n)

        patches_dir = contract_dir / "patches"
        patches_dir.mkdir(parents=True, exist_ok=True)
        mbox = patches_dir / "series.mbox"
        diff_bytes = subprocess.check_output(
            ["git", "-C", str(handle.path), "format-patch",
             f"{handle.base_sha}..HEAD", "--stdout", "--binary"],
        )
        mbox.write_bytes(diff_bytes)
        return PatchSeries(mbox=mbox)
