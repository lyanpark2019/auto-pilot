# PR2 — Worktree Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `isolation: worktree` real — workers run in `git worktree` branches, output is merged via `git format-patch` → `git am --3way` with per-commit trailers; bounded conflict state machine integrates with pivot-detector; orphan reaper cleans abandoned worktrees.

**Architecture:** New module `scripts/_worktree.py` (WorktreeManager class) + `scripts/_status.py` (terminal-status enum). Replaces `headless-loop.py`'s blast-radius `git reset --hard` with per-contract worktree cleanup.

**Tech Stack:** Python stdlib (subprocess, pathlib, fcntl, json, dataclasses), git ≥ 2.32 (for `git am --trailer`).

**Depends on:** PR1 merged (contract layer + `_status` enum location).

---

## File map

- Create: `scripts/_status.py` (WorkerStatus enum, TERMINAL set)
- Create: `scripts/_worktree.py` (WorktreeManager, WorktreeHandle, PatchResult ADTs)
- Create: `tests/test_worktree.py`
- Create: `tests/test_worktree_integration.py`
- Modify: `scripts/headless-loop.py` (replace `git_reset_hard(ROOT)` with per-contract cleanup)
- Modify: `commands/auto-pilot.md` (preflight: `git --version` ≥ 2.32 check)

---

## Task 1: Preflight git version check

**Files:**
- Modify: `commands/auto-pilot.md`
- Modify: `tests/test_hooks.py` (add CLI smoke for the preflight one-liner)

- [ ] **Step 1: Write failing test for the version check shell snippet**

Append to `tests/test_hooks.py`:

```python
def test_git_version_preflight_accepts_232():
    out = subprocess.check_output(
        ["bash", "-c",
         'v=$(git --version | awk "{print \\$3}"); '
         'IFS=. read -r maj min _ <<< "$v"; '
         '[ "$maj" -gt 2 ] || { [ "$maj" -eq 2 ] && [ "$min" -ge 32 ]; } && echo OK || echo FAIL'],
        text=True,
    ).strip()
    # On any modern CI the installed git is ≥ 2.32; expect OK
    assert out == "OK"
```

Run: `pytest tests/test_hooks.py::test_git_version_preflight_accepts_232 -v`
Expected: PASS (modern git is ≥ 2.32 universally)

- [ ] **Step 2: Add the preflight section to `commands/auto-pilot.md`**

Find the "## Pre-flight" section and add as item 6:

```markdown
6. Confirm `git --version` ≥ 2.32 (required for `git am --trailer`):
   ```bash
   v=$(git --version | awk '{print $3}')
   IFS=. read -r maj min _ <<< "$v"
   if ! { [ "$maj" -gt 2 ] || { [ "$maj" -eq 2 ] && [ "$min" -ge 32 ]; }; }; then
     echo "auto-pilot: git $v < 2.32 — required for am --trailer" >&2; exit 2
   fi
   ```
```

- [ ] **Step 3: Commit**

```bash
git add commands/auto-pilot.md tests/test_hooks.py
git commit -m "feat(preflight): require git ≥ 2.32 for am --trailer"
```

---

## Task 2: `_status.py` — WorkerStatus enum

**Files:**
- Create: `scripts/_status.py`
- Create: `tests/test_status.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_status.py`:

```python
"""Tests for scripts/_status.py."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def test_worker_status_values():
    import _status
    assert _status.WorkerStatus.DONE.value == "DONE"
    assert _status.WorkerStatus.DONE_NOOP.value == "DONE_NOOP"
    assert _status.WorkerStatus.BLOCKED.value == "BLOCKED"
    assert _status.WorkerStatus.FAILED.value == "FAILED"
    assert _status.WorkerStatus.CANCELED.value == "CANCELED"
    assert _status.WorkerStatus.PARTIAL.value == "PARTIAL"


def test_terminal_set():
    import _status
    assert _status.WorkerStatus.PARTIAL not in _status.TERMINAL
    assert _status.WorkerStatus.DONE in _status.TERMINAL
    assert _status.WorkerStatus.DONE_NOOP in _status.TERMINAL
    assert _status.WorkerStatus.BLOCKED in _status.TERMINAL
    assert _status.WorkerStatus.FAILED in _status.TERMINAL
    assert _status.WorkerStatus.CANCELED in _status.TERMINAL
```

Run: `pytest tests/test_status.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 2: Create `scripts/_status.py`**

```python
"""Shared terminal-status enum for worker output classification."""
from __future__ import annotations

from enum import Enum


class WorkerStatus(str, Enum):
    DONE       = "DONE"
    DONE_NOOP  = "DONE_NOOP"
    BLOCKED    = "BLOCKED"
    FAILED     = "FAILED"
    CANCELED   = "CANCELED"
    PARTIAL    = "PARTIAL"   # non-terminal; reaper treats as in-flight


TERMINAL: frozenset[WorkerStatus] = frozenset({
    WorkerStatus.DONE,
    WorkerStatus.DONE_NOOP,
    WorkerStatus.BLOCKED,
    WorkerStatus.FAILED,
    WorkerStatus.CANCELED,
})
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_status.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/_status.py tests/test_status.py
git commit -m "feat(status): WorkerStatus enum + TERMINAL set"
```

---

## Task 3: `_worktree.py` skeleton — WorktreeHandle + PatchResult ADTs

**Files:**
- Create: `scripts/_worktree.py`
- Create: `tests/test_worktree.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_worktree.py`:

```python
"""Tests for scripts/_worktree.py."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def test_worktree_handle_serialization(tmp_path):
    import _worktree
    h = _worktree.WorktreeHandle(
        path=tmp_path / "wt",
        branch="auto-pilot/iter-1/phase-1/contract-1/round-1",
        base_sha="abcdef1234567890abcdef1234567890abcdef12",
        contract_id="iter-1/phase-1/contract-1/round-1",
        created_at="2026-05-28T10:00:00+00:00",
    )
    target = tmp_path / "handle.json"
    h.write(target)
    assert target.exists()
    h2 = _worktree.WorktreeHandle.read(target)
    assert h2 == h


def test_patch_result_variants():
    import _worktree
    assert isinstance(_worktree.NoOp(), _worktree.PatchResult)
    assert isinstance(_worktree.NeedsRebase(reason="x", current_base="y"), _worktree.PatchResult)
    assert isinstance(_worktree.RejectMultipleCommits(count=3), _worktree.PatchResult)
    p = Path("/tmp/series.mbox")
    assert isinstance(_worktree.PatchSeries(mbox=p), _worktree.PatchResult)
```

Run: `pytest tests/test_worktree.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 2: Create `scripts/_worktree.py` skeleton**

```python
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
from pathlib import Path


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
        d = json.loads(source.read_text())
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
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_worktree.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/_worktree.py tests/test_worktree.py
git commit -m "feat(worktree): WorktreeHandle + PatchResult ADT skeleton"
```

---

## Task 4: WorktreeManager.create + branch naming + sentinel

**Files:**
- Modify: `scripts/_worktree.py`
- Modify: `tests/test_worktree.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_worktree.py`:

```python
def _init_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    (repo / "a.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    return repo


def _fake_contract(repo_root, contract_dir):
    return {
        "id": "iter-1/phase-1/contract-1/round-1",
        "snapshot_shas": {
            "base_sha": subprocess.check_output(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
            ).strip(),
            "spec": "0" * 64,
            "claude_md_chain": [],
        },
    }


def test_create_makes_worktree_with_canonical_branch(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)

    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)

    assert handle.branch == "auto-pilot/iter-1/phase-1/contract-1/round-1"
    assert handle.path.exists()
    sentinel = handle.path / ".auto-pilot-worktree"
    assert sentinel.exists()
    assert sentinel.read_text().strip() == contract["id"]
    persisted = contract_dir / "worktree-handle.json"
    assert persisted.exists()


def test_create_rejects_invalid_branch_name_with_lock_suffix(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"
    wt_base.mkdir()
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    contract["id"] = "iter-1/phase-1/contract-1/round-1.lock"  # invalid

    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    with pytest.raises(_worktree.InvalidBranchNameError):
        mgr.create(contract, contract_dir=contract_dir)
```

Run: `pytest tests/test_worktree.py -v -k 'create'`
Expected: FAIL (AttributeError).

- [ ] **Step 2: Implement WorktreeManager.create**

Append to `scripts/_worktree.py`:

```python
class InvalidBranchNameError(Exception):
    """Branch name fails `git check-ref-format`."""


class WorktreeManager:
    """Owns the lifecycle of git worktrees for auto-pilot workers."""

    def __init__(self, *, repo_root: Path, worktree_base: Path) -> None:
        self.repo_root = repo_root
        self.worktree_base = worktree_base

    def create(self, contract: dict, *, contract_dir: Path) -> WorktreeHandle:
        """Create a worktree on the canonical branch derived from contract.id.

        1. Validate branch name via `git check-ref-format`.
        2. `git -C $ROOT worktree add <wt_path> -b <branch> <base_sha>`.
        3. Write `.auto-pilot-worktree` sentinel containing contract.id inside wt.
        4. Persist WorktreeHandle to `<contract_dir>/worktree-handle.json`.
        """
        from datetime import datetime, timezone
        contract_id = contract["id"]
        branch = f"auto-pilot/{contract_id}"
        # check-ref-format
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
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_worktree.py -v -k 'create'`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/_worktree.py tests/test_worktree.py
git commit -m "feat(worktree): WorktreeManager.create with sentinel + handle persistence"
```

---

## Task 5: WorktreeManager.collect_patches — ancestry + single-commit + no-op

**Files:**
- Modify: `scripts/_worktree.py`
- Modify: `tests/test_worktree.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_worktree.py`:

```python
def _commit_one(repo, name, content):
    (repo / name).write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", name], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", f"add {name}"], check=True)


def test_collect_patches_returns_noop_on_empty_diff(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    # No commits in worktree → no diff
    result = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(result, _worktree.NoOp)


def test_collect_patches_returns_patch_series_on_single_commit(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "second\n")
    result = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(result, _worktree.PatchSeries)
    assert result.mbox.exists()
    assert result.mbox.read_bytes().startswith(b"From ")


def test_collect_patches_rejects_multiple_commits(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "1\n")
    _commit_one(handle.path, "c.txt", "2\n")
    result = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(result, _worktree.RejectMultipleCommits)
    assert result.count == 2


def test_collect_patches_returns_needs_rebase_when_not_ancestor(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    # Reset worktree HEAD to a different commit not descending from base
    _commit_one(repo, "z.txt", "z\n")  # advance main
    subprocess.run(["git", "-C", str(handle.path), "reset", "--hard", "main"], check=True)
    # Now HEAD does descend, force divergence:
    subprocess.run(["git", "-C", str(handle.path), "checkout", "--orphan", "orphan-branch"], check=True)
    _commit_one(handle.path, "o.txt", "o\n")
    result = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(result, _worktree.NeedsRebase)
```

Run: `pytest tests/test_worktree.py -v -k 'collect_patches'`
Expected: FAIL.

- [ ] **Step 2: Implement collect_patches**

Append to `scripts/_worktree.py`:

```python
    def collect_patches(self, handle: WorktreeHandle, *, contract_dir: Path) -> PatchResult:
        """Inspect worker's worktree HEAD vs base_sha; return one of NoOp,
        NeedsRebase, RejectMultipleCommits, PatchSeries."""
        # Ancestry check
        ancestry = subprocess.run(
            ["git", "-C", str(handle.path), "merge-base", "--is-ancestor",
             handle.base_sha, "HEAD"],
            capture_output=True, text=True,
        )
        if ancestry.returncode != 0:
            # current_base = best-effort common ancestor of HEAD and base_sha
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
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_worktree.py -v -k 'collect_patches'`
Expected: PASS (all 4)

- [ ] **Step 4: Commit**

```bash
git add scripts/_worktree.py tests/test_worktree.py
git commit -m "feat(worktree): collect_patches with ancestry + count discriminator"
```

---

## Task 6: WorktreeManager.apply_to_main — am --3way + trailers + lock + stale recovery

**Files:**
- Modify: `scripts/_worktree.py`
- Modify: `tests/test_worktree.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_worktree.py`:

```python
def test_apply_to_main_lands_commit_with_trailers(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    contract["idempotency_token"] = "deadbeef00112233"
    contract["iter"] = 1
    contract["phase"] = 1
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "x\n")
    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)

    result = mgr.apply_to_main(series.mbox, contract)
    assert result.status == "applied"

    # Trailer chain check
    log = subprocess.check_output(
        ["git", "-C", str(repo), "log", "-1", "--format=%B"],
        text=True,
    )
    assert "auto-pilot-iter: 1" in log
    assert "auto-pilot-phase: 1" in log
    assert "auto-pilot-contract: iter-1/phase-1/contract-1/round-1" in log
    assert "auto-pilot-idempotency: deadbeef00112233" in log


def test_apply_to_main_aborts_on_conflict(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    # Worker edits a.txt
    (handle.path / "a.txt").write_text("worker-version\n")
    subprocess.run(["git", "-C", str(handle.path), "commit", "-q", "-am", "wt edit"], check=True)
    # Main also edits a.txt (concurrent)
    (repo / "a.txt").write_text("main-version\n")
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-am", "main edit"], check=True)

    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)
    result = mgr.apply_to_main(series.mbox, contract)
    assert result.status == "conflict"

    # Repo cleanly back at main HEAD
    status = subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain"], text=True
    ).strip()
    assert status == ""
    assert not (repo / ".git" / "rebase-apply").exists()


def test_apply_to_main_clears_stale_rebase_apply(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    # Simulate stale .git/rebase-apply from a prior crashed run
    stale = repo / ".git" / "rebase-apply"
    stale.mkdir()
    (stale / "stale-marker").write_text("x")

    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "x\n")
    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)
    result = mgr.apply_to_main(series.mbox, contract)
    assert result.status == "applied"
    assert not (repo / ".git" / "rebase-apply").exists()


def test_apply_to_main_refuses_dirty_main(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    (repo / "dirty.txt").write_text("untracked")  # dirty main
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    _commit_one(handle.path, "b.txt", "x\n")
    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)
    with pytest.raises(_worktree.MainTreeDirtyError):
        mgr.apply_to_main(series.mbox, contract)
```

Run: `pytest tests/test_worktree.py -v -k 'apply_to_main'`
Expected: FAIL.

- [ ] **Step 2: Implement apply_to_main**

Append to `scripts/_worktree.py`:

```python
import fcntl
from contextlib import contextmanager
from typing import Iterator


@dataclass(frozen=True)
class ApplyResult:
    status: str  # "applied" | "conflict"
    main_sha: str | None = None
    pre_apply_head: str | None = None
    conflict_files: tuple[str, ...] = ()


class MainTreeDirtyError(Exception):
    """git status --porcelain not empty on $ROOT when apply_to_main acquired lock."""


class StaleAmStateError(Exception):
    """`.git/rebase-apply` still exists after auto-abort attempt; human intervention required."""


    @contextmanager
    def _main_apply_lock(self) -> Iterator[None]:
        # Note: this method is added inside WorktreeManager; in Python it must
        # be defined at class scope. See Step 3 for how to merge.
        ...
```

Actually merge cleanly — replace the prior single-line method definitions with the full WorktreeManager class addition. Use this complete addition (append after the existing class body):

```python
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
        return subprocess.check_output(
            ["git", "-C", str(self.repo_root), "status", "--porcelain", "--untracked-files=all"],
            text=True,
        )

    def _head_sha(self) -> str:
        return subprocess.check_output(
            ["git", "-C", str(self.repo_root), "rev-parse", "HEAD"], text=True
        ).strip()

    def apply_to_main(self, mbox: Path, contract: dict) -> ApplyResult:
        """Apply worker's patch series to main repo with trailers, under lock.

        Sequence:
          1. Acquire main-apply.lock.
          2. Preflight: stale .git/rebase-apply → abort, raise if not recoverable.
          3. Post-acquire: dirty main → MainTreeDirtyError.
          4. git am --3way --keep-cr --trailer ... <mbox>.
          5. Conflict → abort, return ApplyResult(status='conflict').
          6. Success → return ApplyResult(status='applied', main_sha=...).
        """
        with self._main_apply_lock():
            rebase_apply = self.repo_root / ".git" / "rebase-apply"
            if rebase_apply.exists():
                subprocess.run(
                    ["git", "-C", str(self.repo_root), "am", "--abort"],
                    capture_output=True, check=False,
                )
                if rebase_apply.exists():
                    raise StaleAmStateError(f"could not clear {rebase_apply}")

            dirty = self._is_dirty()
            if dirty.strip():
                raise MainTreeDirtyError(dirty)

            pre = self._head_sha()
            trailers = [
                "--trailer", f"auto-pilot-iter: {contract['iter']}",
                "--trailer", f"auto-pilot-phase: {contract['phase']}",
                "--trailer", f"auto-pilot-contract: {contract['id']}",
                "--trailer", f"auto-pilot-idempotency: {contract['idempotency_token']}",
            ]
            am = subprocess.run(
                ["git", "-C", str(self.repo_root), "am", "--3way", "--keep-cr",
                 *trailers, str(mbox)],
                capture_output=True, text=True,
            )
            if am.returncode != 0:
                # Conflict or other failure
                conflict_files: tuple[str, ...] = ()
                if rebase_apply.exists():
                    pf = rebase_apply / "patch"
                    if pf.exists():
                        # Best-effort: extract paths from patch headers
                        files = [
                            line[len("diff --git a/"):].split(" b/")[0]
                            for line in pf.read_text(errors="replace").splitlines()
                            if line.startswith("diff --git a/")
                        ]
                        conflict_files = tuple(sorted(set(files)))
                subprocess.run(
                    ["git", "-C", str(self.repo_root), "am", "--abort"],
                    capture_output=True, check=False,
                )
                return ApplyResult(status="conflict", pre_apply_head=pre,
                                   conflict_files=conflict_files)
            return ApplyResult(status="applied", main_sha=self._head_sha(),
                               pre_apply_head=pre)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_worktree.py -v -k 'apply_to_main'`
Expected: PASS (all 4)

- [ ] **Step 4: Commit**

```bash
git add scripts/_worktree.py tests/test_worktree.py
git commit -m "feat(worktree): apply_to_main with am --trailer + lock + stale recovery"
```

---

## Task 7: WorktreeManager.cleanup (idempotent) + rehydrate

**Files:**
- Modify: `scripts/_worktree.py`
- Modify: `tests/test_worktree.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_worktree.py`:

```python
def test_cleanup_removes_worktree_and_branch(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    assert handle.path.exists()

    mgr.cleanup(handle, prune_branch=True)
    assert not handle.path.exists()
    # Branch gone
    branches = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "-a"], text=True
    )
    assert handle.branch not in branches


def test_cleanup_idempotent(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contract_dir)
    mgr.cleanup(handle, prune_branch=True)
    # Second call must not raise
    mgr.cleanup(handle, prune_branch=True)


def test_rehydrate_reads_persisted_handle(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = _fake_contract(repo, contract_dir)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    original = mgr.create(contract, contract_dir=contract_dir)

    # Simulate PM restart: rehydrate from disk
    rehydrated = mgr.rehydrate(contract_dir)
    assert rehydrated == original


def test_rehydrate_returns_none_if_no_handle(tmp_path):
    import _worktree
    mgr = _worktree.WorktreeManager(repo_root=tmp_path, worktree_base=tmp_path / "wt")
    contract_dir = tmp_path / "no-handle-here"
    contract_dir.mkdir()
    assert mgr.rehydrate(contract_dir) is None
```

Run: `pytest tests/test_worktree.py -v -k 'cleanup or rehydrate'`
Expected: FAIL (AttributeError).

- [ ] **Step 2: Implement**

Append to `scripts/_worktree.py`:

```python
    def cleanup(self, handle: WorktreeHandle, *, prune_branch: bool) -> None:
        """Idempotent: tolerate missing worktree, branch, sentinel."""
        subprocess.run(
            ["git", "-C", str(self.repo_root), "worktree", "remove", "--force",
             str(handle.path)],
            capture_output=True, check=False,
        )
        # Force-prune metadata in case worktree dir was already removed manually
        subprocess.run(
            ["git", "-C", str(self.repo_root), "worktree", "prune"],
            capture_output=True, check=False,
        )
        if prune_branch:
            subprocess.run(
                ["git", "-C", str(self.repo_root), "branch", "-D", handle.branch],
                capture_output=True, check=False,
            )

    def rehydrate(self, contract_dir: Path) -> WorktreeHandle | None:
        """Reconstruct WorktreeHandle from <contract_dir>/worktree-handle.json after PM restart."""
        handle_path = contract_dir / "worktree-handle.json"
        if not handle_path.exists():
            return None
        return WorktreeHandle.read(handle_path)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_worktree.py -v -k 'cleanup or rehydrate'`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/_worktree.py tests/test_worktree.py
git commit -m "feat(worktree): cleanup idempotent + rehydrate from disk"
```

---

## Task 8: WorktreeManager.reap_orphans

**Files:**
- Modify: `scripts/_worktree.py`
- Modify: `tests/test_worktree.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_worktree.py`:

```python
import time, os


def test_reap_orphans_removes_terminal_aged_worktrees(tmp_path):
    import _worktree, _status, json as _json
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    state_dir = tmp_path / ".planning" / "auto-pilot"
    contracts_root = state_dir / "contracts" / "iter-1" / "phase-1" / "contract-1" / "round-1"
    contracts_root.mkdir(parents=True)
    contract = _fake_contract(repo, contracts_root)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contracts_root)
    # Worker status terminal + done.marker
    (contracts_root / "outputs" / "worker").mkdir(parents=True)
    (contracts_root / "outputs" / "worker" / "status.json").write_text(
        _json.dumps({"status": _status.WorkerStatus.DONE.value}))
    (contracts_root / "outputs" / "worker" / "done.marker").touch()
    # Backdate sentinel to look old
    old = time.time() - 48 * 3600
    os.utime(handle.path / ".auto-pilot-worktree", (old, old))

    reaped = mgr.reap_orphans(state_dir=state_dir, max_age_hours=24)
    assert handle.path in reaped


def test_reap_orphans_preserves_in_flight(tmp_path):
    import _worktree
    repo = _init_repo(tmp_path)
    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    state_dir = tmp_path / ".planning" / "auto-pilot"
    contracts_root = state_dir / "contracts" / "iter-1" / "phase-1" / "contract-1" / "round-1"
    contracts_root.mkdir(parents=True)
    contract = _fake_contract(repo, contracts_root)
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)
    handle = mgr.create(contract, contract_dir=contracts_root)
    # No status.json, no done.marker → in-flight
    reaped = mgr.reap_orphans(state_dir=state_dir, max_age_hours=0)
    assert handle.path not in reaped
```

Run: `pytest tests/test_worktree.py -v -k 'reap_orphans'`
Expected: FAIL.

- [ ] **Step 2: Implement**

Append to `scripts/_worktree.py`:

```python
import json as _json_mod

import _status


    def reap_orphans(self, *, state_dir: Path, max_age_hours: int = 24) -> list[Path]:
        """Reap worktrees whose contract has terminal status past age threshold.

        Returns list of reaped worktree paths.
        """
        cutoff = __import__("time").time() - max_age_hours * 3600
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
            data = _json_mod.loads(status_json.read_text())
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
                # Fallback: remove worktree without handle (best-effort)
                subprocess.run(
                    ["git", "-C", str(self.repo_root), "worktree", "remove",
                     "--force", str(wt_path)],
                    capture_output=True, check=False,
                )
            reaped.append(wt_path)
        return reaped
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_worktree.py -v -k 'reap_orphans'`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/_worktree.py tests/test_worktree.py
git commit -m "feat(worktree): reap_orphans keyed on sentinel + terminal status"
```

---

## Task 9: Bounded conflict state machine — feeds pivot-detector

**Files:**
- Modify: `scripts/_worktree.py`
- Modify: `tests/test_worktree.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_worktree.py`:

```python
def test_compute_merge_conflict_finding_hash():
    import _worktree
    h1 = _worktree.compute_merge_conflict_finding_hash(["src/a.py", "src/b.py"])
    h2 = _worktree.compute_merge_conflict_finding_hash(["src/b.py", "src/a.py"])  # order-insensitive
    assert h1 == h2
    h3 = _worktree.compute_merge_conflict_finding_hash(["src/a.py"])
    assert h1 != h3
```

Run: `pytest tests/test_worktree.py::test_compute_merge_conflict_finding_hash -v`
Expected: FAIL.

- [ ] **Step 2: Implement helper**

Append to `scripts/_worktree.py`:

```python
import hashlib


MAX_MERGE_ATTEMPTS = 3


def compute_merge_conflict_finding_hash(conflict_files: list[str]) -> str:
    """Deterministic hash for pivot-detector keyed on sorted conflict file set."""
    payload = "merge_conflict:" + ",".join(sorted(set(conflict_files)))
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 3: Run test**

Run: `pytest tests/test_worktree.py::test_compute_merge_conflict_finding_hash -v`
Expected: PASS

- [ ] **Step 4: Document state machine in agents/pm-orchestrator.md**

Append to `agents/pm-orchestrator.md`:

```markdown
## Merge conflict state machine (v1)

When `WorktreeManager.apply_to_main` returns `ApplyResult(status='conflict')`:
1. PM increments `contract.merge_attempts` (default 0).
2. PM dispatches a rebase contract with `acceptance: ["rebase onto new base_sha, preserve diff"]` (reuses existing worker, no new conflict-resolver subagent).
3. After 3 failed attempts, PM marks `contract.status = merge_pivot_needed`.
4. Failure feeds the existing pivot-detector via `finding_hash = _worktree.compute_merge_conflict_finding_hash(conflict_files)`.
5. Counter resets per-contract (not per-phase, not global).
```

- [ ] **Step 5: Commit**

```bash
git add scripts/_worktree.py tests/test_worktree.py agents/pm-orchestrator.md
git commit -m "feat(worktree): bounded conflict SM + finding-hash for pivot-detector"
```

---

## Task 10: Replace headless-loop blast-radius reset with per-contract cleanup

**Files:**
- Modify: `scripts/headless-loop.py`
- Modify: `tests/test_headless_loop.py`

- [ ] **Step 1: Write failing test that captures intended behavior**

Append to `tests/test_headless_loop.py`:

```python
def test_loop_iteration_does_not_call_git_reset_hard_on_root(monkeypatch, tmp_path):
    """After PR2, failed phase must NOT git-reset --hard ROOT (blast radius).
    Worktree cleanup is the recovery unit."""
    import sys, importlib
    monkeypatch.chdir(tmp_path)
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    import _state
    importlib.reload(_state)
    import headless_loop as loop_module  # may need rename to importable form
    importlib.reload(loop_module)

    calls = []

    def fake_reset(sha):
        calls.append(("reset", sha))

    monkeypatch.setattr(loop_module, "git_reset_hard", fake_reset)
    monkeypatch.setattr(loop_module, "run_claude_session", lambda *a, **k: 0)

    # Simulate a state where phase ended FAILED
    (tmp_path / ".planning" / "auto-pilot").mkdir(parents=True)
    (tmp_path / ".planning" / "auto-pilot" / "state.json").write_text(json.dumps({
        "started_at": "2026-05-28T10:00:00+00:00",
        "spec_path": "spec.md", "current_phase": 1, "total_phases": 2,
        "status": "failed", "max_workers": 1, "phases": [
            {"phase": 1, "status": "failed", "round": 1, "contracts": 1,
             "approved": 0, "started": "2026-05-28T10:00:00+00:00", "ended": "2026-05-28T10:05:00+00:00",
             "commits": []}
        ], "pivot_detector": {}
    }))

    args = type("A", (), {"timeout_build": 5})
    status = loop_module.loop_iteration(1, args)
    assert status == "failed"
    assert not any(c[0] == "reset" for c in calls), \
        "headless-loop must not call git_reset_hard on $ROOT after PR2"
```

Run: `pytest tests/test_headless_loop.py::test_loop_iteration_does_not_call_git_reset_hard_on_root -v`
Expected: FAIL (test will likely either fail because `git_reset_hard` is still called OR because the import/structure assumptions don't match yet).

- [ ] **Step 2: Modify `scripts/headless-loop.py` `loop_iteration`**

Locate the block:
```python
    if status == "failed":
        event("iter.fail_rollback", pre_head=pre_head[:8])
        git_reset_hard(pre_head)

    return status
```

Replace with:
```python
    if status == "failed":
        event("iter.fail_no_root_reset",
              note="per PR2: $ROOT untouched on phase fail; worktree cleanup is the recovery unit")
        # NOTE: per-contract worktree cleanup happens inside the PM session via
        # scripts/_worktree.WorktreeManager.cleanup(handle, prune_branch=True).
        # The outer driver no longer touches $ROOT.

    return status
```

Also remove the timeout-rollback `git_reset_hard` call (per PR2 same rationale) — keep state mark as failed:
```python
    if rc == 124:
        event("iter.timeout_no_root_reset",
              pre_head=pre_head[:8],
              note="state.status set to failed; $ROOT untouched")
        # Mark state failed so next iter sees terminal
        state2 = load_state()
        state2["status"] = "failed"
        from _state import save_state
        save_state(state2)
        return "failed"
```

- [ ] **Step 3: Run test**

Run: `pytest tests/test_headless_loop.py::test_loop_iteration_does_not_call_git_reset_hard_on_root -v`
Expected: PASS

- [ ] **Step 4: Run full headless-loop test file to catch regressions**

Run: `pytest tests/test_headless_loop.py -v`
Expected: all pass (some may need adjustment if they asserted the old behavior).

- [ ] **Step 5: Commit**

```bash
git add scripts/headless-loop.py tests/test_headless_loop.py
git commit -m "fix(headless): drop blast-radius git-reset-hard ROOT; mark state failed instead"
```

---

## Task 11: Integration test — end-to-end create → commit → apply

**Files:**
- Create: `tests/test_worktree_integration.py`

- [ ] **Step 1: Write the integration test**

Create `tests/test_worktree_integration.py`:

```python
"""End-to-end worktree lifecycle integration test."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def test_full_lifecycle(tmp_path):
    """create → worker edits → collect_patches → apply_to_main → cleanup."""
    import _worktree
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    (repo / "src.py").write_text("def f(): return 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "src.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True)
    base = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()

    wt_base = tmp_path / "worktrees"; wt_base.mkdir()
    contract_dir = tmp_path / "contract"; contract_dir.mkdir()
    contract = {
        "id": "iter-1/phase-1/contract-1/round-1",
        "iter": 1, "phase": 1,
        "idempotency_token": "abcd1234abcd1234",
        "snapshot_shas": {"base_sha": base, "spec": "0" * 64, "claude_md_chain": []},
    }
    mgr = _worktree.WorktreeManager(repo_root=repo, worktree_base=wt_base)

    # 1. create
    handle = mgr.create(contract, contract_dir=contract_dir)

    # 2. worker edits + single commit
    (handle.path / "src.py").write_text("def f(): return 42\n")
    subprocess.run(["git", "-C", str(handle.path), "commit", "-q", "-am", "fix f"], check=True)

    # 3. collect patches
    series = mgr.collect_patches(handle, contract_dir=contract_dir)
    assert isinstance(series, _worktree.PatchSeries)

    # 4. apply to main
    result = mgr.apply_to_main(series.mbox, contract)
    assert result.status == "applied"
    assert (repo / "src.py").read_text() == "def f(): return 42\n"

    # 5. trailers present
    log = subprocess.check_output(["git", "-C", str(repo), "log", "-1", "--format=%B"], text=True)
    assert "auto-pilot-iter: 1" in log
    assert "auto-pilot-contract: iter-1/phase-1/contract-1/round-1" in log

    # 6. cleanup
    mgr.cleanup(handle, prune_branch=True)
    assert not handle.path.exists()
```

- [ ] **Step 2: Run test**

Run: `pytest tests/test_worktree_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_worktree_integration.py
git commit -m "test(worktree): end-to-end integration"
```

---

## Task 12: PR2 final smoke + push

**Files:**
- None new

- [ ] **Step 1: Run entire test suite**

Run: `pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 2: Run mypy + ruff**

Run: `mypy scripts/`
Run: `ruff check scripts/ tests/`
Expected: clean

- [ ] **Step 3: Push branch + open PR**

```bash
git push -u origin auto-pilot/p2-worktree
gh pr create --title "PR2: worktree lifecycle" --body "$(cat <<'EOF'
## Summary
- Add `scripts/_status.py` (WorkerStatus enum + TERMINAL set)
- Add `scripts/_worktree.py` (WorktreeManager + ADT PatchResult)
- Replace `headless-loop.py` blast-radius `git reset --hard $ROOT` with per-contract worktree cleanup
- Document merge conflict state machine in `agents/pm-orchestrator.md`
- Preflight requires `git ≥ 2.32` for `am --trailer`

## Test plan
- [ ] pytest tests/ passes incl. test_worktree_integration.py
- [ ] mypy + ruff clean
- [ ] `git am` stale-state preflight recovers
- [ ] dirty main rejected
- [ ] sentinel + handle persist for crash-resume
- [ ] reaper preserves in-flight, removes terminal aged

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Done

PR2 merged. With PR1 + PR2 (and PR3 not yet) + `AUTO_PILOT_DISABLE_NEW_REVIEWERS=1`, system runs Tier 1 dogfood.
