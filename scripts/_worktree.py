"""Worktree lifecycle for auto-pilot workers.

Invariant: only $ROOT (main repo) calls these; worktrees are ephemeral.
All ops use `git -C <path>` — never relies on cwd.

Locking: apply_to_main holds .planning/auto-pilot/main-apply.lock (flock).
All mutations of $ROOT (not worktrees) MUST go through WorktreeManager.apply_to_main().
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, cast

import _status
from _log import event

# Subprocess timeout budget (seconds). Quick git plumbing vs. tree-touching ops.
_GIT_QUICK_TIMEOUT = 30  # rev-parse, status, branch, merge-base, rev-list, ref-format, prune
_GIT_TREE_TIMEOUT = 60  # worktree add/remove, am, format-patch, commit --amend (touch large trees)


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


class MainTreeDirtyError(Exception):
    """git status --porcelain not empty on $ROOT when apply_to_main acquired lock."""


class StaleAmStateError(Exception):
    """`.git/rebase-apply` still exists after auto-abort attempt; human intervention required."""


@dataclass(frozen=True)
class ApplyResult:
    status: str  # "applied" | "conflict"
    main_sha: str | None = None
    pre_apply_head: str | None = None
    conflict_files: tuple[str, ...] = ()


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

        Raises:
            InvalidBranchNameError: branch name fails `git check-ref-format`.
            subprocess.CalledProcessError: `git worktree add` exits non-zero.
            subprocess.TimeoutExpired: a git op stalls past its timeout
                (30 s for ref-check, 60 s for `worktree add`). One-shot caller;
                a stalled create is a hard failure, not a degrade case.
        """
        contract_id = contract["id"]
        branch = f"auto-pilot/{contract_id}"
        refcheck = subprocess.run(
            ["git", "check-ref-format", f"refs/heads/{branch}"],
            capture_output=True, text=True, timeout=_GIT_QUICK_TIMEOUT,
        )
        if refcheck.returncode != 0:
            raise InvalidBranchNameError(f"{branch!r}: {refcheck.stderr.strip()}")

        wt_path = self.worktree_base / contract_id
        wt_path.parent.mkdir(parents=True, exist_ok=True)

        base_sha = contract["snapshot_shas"]["base_sha"]
        subprocess.run(
            ["git", "-C", str(self.repo_root), "worktree", "add",
             str(wt_path), "-b", branch, base_sha],
            check=True, capture_output=True, timeout=_GIT_TREE_TIMEOUT,
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
        NeedsRebase, RejectMultipleCommits, PatchSeries.

        Raises:
            subprocess.CalledProcessError: `rev-list`/`format-patch` exit non-zero.
            subprocess.TimeoutExpired: a git op stalls past its timeout (30 s for
                merge-base/rev-list plumbing, 60 s for `format-patch` which may
                serialize a large diff). One-shot caller; not a degrade case.
        """
        ancestry = subprocess.run(
            ["git", "-C", str(handle.path), "merge-base", "--is-ancestor",
             handle.base_sha, "HEAD"],
            capture_output=True, text=True, timeout=_GIT_QUICK_TIMEOUT,
        )
        if ancestry.returncode != 0:
            try:
                cb = subprocess.check_output(
                    ["git", "-C", str(handle.path), "merge-base",
                     handle.base_sha, "HEAD"],
                    text=True, timeout=_GIT_QUICK_TIMEOUT,
                ).strip()
            except subprocess.CalledProcessError:
                cb = ""
            return NeedsRebase(reason="HEAD does not descend from base_sha",
                                current_base=cb)

        count_out = subprocess.check_output(
            ["git", "-C", str(handle.path), "rev-list", "--count",
             f"{handle.base_sha}..HEAD"],
            text=True, timeout=_GIT_QUICK_TIMEOUT,
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
            timeout=_GIT_TREE_TIMEOUT,
        )
        mbox.write_bytes(diff_bytes)
        return PatchSeries(mbox=mbox)

    @contextmanager
    def _main_apply_lock(self) -> Iterator[None]:
        lock_dir = self.repo_root / ".planning" / "auto-pilot"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / "main-apply.lock"
        lock_path.touch(exist_ok=True)
        fd = lock_path.open("r+")
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            finally:
                fd.close()

    def _is_dirty(self) -> str:
        """Raises subprocess.TimeoutExpired if `git status` stalls past 30 s."""
        return subprocess.check_output(
            ["git", "-C", str(self.repo_root), "status", "--porcelain", "--untracked-files=all"],
            text=True, timeout=_GIT_QUICK_TIMEOUT,
        )

    def _head_sha(self) -> str:
        """Raises subprocess.TimeoutExpired if `git rev-parse` stalls past 30 s."""
        return subprocess.check_output(
            ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"], text=True,
            timeout=_GIT_QUICK_TIMEOUT,
        ).strip()

    def apply_to_main(self, mbox: Path, contract: dict[str, Any]) -> ApplyResult:
        """Apply worker's patch series to main repo with trailers, under lock.

        Sequence:
          1. Acquire main-apply.lock.
          2. Preflight: stale .git/rebase-apply → abort, raise if not recoverable.
          3. Post-acquire: dirty main → MainTreeDirtyError.
          4. git am --3way --keep-cr <mbox>.
          5. Conflict → abort, return ApplyResult(status='conflict').
          6. Success → amend HEAD to inject trailers, return ApplyResult(status='applied').

        Note: `git am` has no --trailer flag. We apply the patch first, then
        `git commit --amend --no-edit --trailer ...` mutates only HEAD, which IS
        the just-applied commit (one-commit invariant enforced by collect_patches).

        Raises:
            MainTreeDirtyError: $ROOT dirty after lock acquired.
            StaleAmStateError: `.git/rebase-apply` survives auto-abort.
            subprocess.TimeoutExpired: a git op stalls past 60 s. Propagation is
                safe — the `_main_apply_lock()` context manager releases the
                flock in its `finally`, so a stall does not leak the lock; the
                caller already treats this method as raising.
        """
        with self._main_apply_lock():
            rebase_apply = self.repo_root / ".git" / "rebase-apply"
            if rebase_apply.exists():
                subprocess.run(
                    ["git", "-C", str(self.repo_root), "am", "--abort"],
                    capture_output=True, check=False, timeout=_GIT_TREE_TIMEOUT,
                )
                if rebase_apply.exists():
                    raise StaleAmStateError(f"could not clear {rebase_apply}")

            dirty = self._is_dirty()
            if dirty.strip():
                raise MainTreeDirtyError(dirty)

            pre = self._head_sha()
            # am has no --trailer; amend HEAD to inject after successful apply
            am = subprocess.run(
                ["git", "-C", str(self.repo_root), "am", "--3way", "--keep-cr",
                 str(mbox)],
                capture_output=True, text=True, timeout=_GIT_TREE_TIMEOUT,
            )
            if am.returncode != 0:
                conflict_files: tuple[str, ...] = ()
                if rebase_apply.exists():
                    pf = rebase_apply / "patch"
                    if pf.exists():
                        files = [
                            line[len("diff --git a/"):].split(" b/")[0]
                            for line in pf.read_text(errors="replace").splitlines()
                            if line.startswith("diff --git a/")
                        ]
                        conflict_files = tuple(sorted(set(files)))
                subprocess.run(
                    ["git", "-C", str(self.repo_root), "am", "--abort"],
                    capture_output=True, check=False, timeout=_GIT_TREE_TIMEOUT,
                )
                return ApplyResult(status="conflict", pre_apply_head=pre,
                                   conflict_files=conflict_files)

            trailers = [
                "--trailer", f"auto-pilot-iter: {contract['iter']}",
                "--trailer", f"auto-pilot-phase: {contract['phase']}",
                "--trailer", f"auto-pilot-contract: {contract['id']}",
                "--trailer", f"auto-pilot-idempotency: {contract['idempotency_token']}",
            ]
            amend = subprocess.run(
                ["git", "-C", str(self.repo_root), "commit", "--amend", "--no-edit",
                 *trailers],
                capture_output=True, text=True, timeout=_GIT_TREE_TIMEOUT,
            )
            if amend.returncode != 0:
                # Best-effort: leave applied commit as-is (no trailer chain)
                return ApplyResult(status="applied", main_sha=self._head_sha(),
                                   pre_apply_head=pre)
            return ApplyResult(status="applied", main_sha=self._head_sha(),
                               pre_apply_head=pre)

    def cleanup(self, handle: WorktreeHandle, *, prune_branch: bool) -> None:
        """Idempotent: tolerate missing worktree, branch, sentinel.

        Degrades on stall: each git op is best-effort (`check=False`); a
        TimeoutExpired is caught and logged rather than raised, so the
        idempotency contract holds even when called in a reap loop. A stalled
        cleanup leaves stale worktree/branch metadata that a later `worktree
        prune` or reap pass can still clear.
        """
        try:
            subprocess.run(
                ["git", "-C", str(self.repo_root), "worktree", "remove", "--force",
                 str(handle.path)],
                capture_output=True, check=False, timeout=_GIT_TREE_TIMEOUT,
            )
            # Force-prune metadata in case worktree dir was already removed manually
            subprocess.run(
                ["git", "-C", str(self.repo_root), "worktree", "prune"],
                capture_output=True, check=False, timeout=_GIT_QUICK_TIMEOUT,
            )
            if prune_branch:
                subprocess.run(
                    ["git", "-C", str(self.repo_root), "branch", "-D", handle.branch],
                    capture_output=True, check=False, timeout=_GIT_QUICK_TIMEOUT,
                )
        except subprocess.TimeoutExpired as exc:
            # Best-effort cleanup; a stall must not crash an idempotent op or a
            # reap loop. Mirror stash_if_dirty: event + graceful degrade.
            event("worktree.cleanup.timeout",
                  contract_id=handle.contract_id,
                  branch=handle.branch,
                  cmd=" ".join(str(a) for a in (exc.cmd or [])))

    def rehydrate(self, contract_dir: Path) -> WorktreeHandle | None:
        """Reconstruct WorktreeHandle from <contract_dir>/worktree-handle.json after PM restart."""
        handle_path = contract_dir / "worktree-handle.json"
        if not handle_path.exists():
            return None
        return WorktreeHandle.read(handle_path)

    def reap_orphans(self, *, state_dir: Path, max_age_hours: int = 24) -> list[Path]:
        """Reap worktrees whose contract has terminal status past age threshold.

        Returns list of reaped worktree paths.
        """
        cutoff = time.time() - max_age_hours * 3600
        reaped: list[Path] = []
        contracts_root = state_dir / "contracts"
        if not contracts_root.exists():
            return reaped

        # Walk all worktrees by sentinel
        for sentinel in self.worktree_base.rglob(".auto-pilot-worktree"):
            try:
                if sentinel.stat().st_mtime > cutoff:
                    continue
            except FileNotFoundError:
                continue
            contract_id = sentinel.read_text().strip()
            contract_dir = contracts_root / contract_id
            status_json = contract_dir / "outputs" / "worker" / "status.json"
            done_marker = contract_dir / "outputs" / "worker" / "done.marker"
            if not done_marker.exists():
                continue  # in-flight or zombie; keep
            if not status_json.exists():
                continue
            data = json.loads(status_json.read_text())
            status_val = data.get("status")
            try:
                status_enum = _status.WorkerStatus(status_val)
            except ValueError:
                continue
            if status_enum not in _status.TERMINAL:
                continue
            wt_path = sentinel.parent
            handle_path = contract_dir / "worktree-handle.json"
            if handle_path.exists():
                handle = WorktreeHandle.read(handle_path)
                self.cleanup(handle, prune_branch=True)
            else:
                # Fallback: remove worktree without handle (best-effort).
                # Degrade on stall — an uncaught TimeoutExpired would abort the
                # reap loop and strand the remaining orphans. Skip this one and
                # continue so the next pass can retry it.
                try:
                    subprocess.run(
                        ["git", "-C", str(self.repo_root), "worktree", "remove",
                         "--force", str(wt_path)],
                        capture_output=True, check=False, timeout=_GIT_TREE_TIMEOUT,
                    )
                except subprocess.TimeoutExpired:
                    event("worktree.reap.timeout", contract_id=contract_id,
                          wt_path=str(wt_path))
                    continue
            reaped.append(wt_path)
        return reaped


MAX_MERGE_ATTEMPTS = 3


def compute_merge_conflict_finding_hash(conflict_files: list[str]) -> str:
    """Deterministic hash for pivot-detector keyed on sorted conflict file set."""
    payload = "merge_conflict:" + ",".join(sorted(set(conflict_files)))
    return hashlib.sha256(payload.encode()).hexdigest()
