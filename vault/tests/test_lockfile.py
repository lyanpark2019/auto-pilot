"""Tests for VaultLock: acquire/release/contention/stale steal."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from lockfile import LockHeldError, VaultLock


def test_acquire_release(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    lock = VaultLock(vault, role="pm-loop")
    lock.acquire()
    assert lock.lock_path.exists()
    held = json.loads(lock.lock_path.read_text())
    assert held["pid"] == os.getpid()
    lock.release()
    assert not lock.lock_path.exists()


def test_concurrent_acquire_blocks(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    lock1 = VaultLock(vault)
    lock1.acquire()
    lock2 = VaultLock(vault)
    with pytest.raises(LockHeldError, match="held by pid"):
        lock2.acquire()
    lock1.release()


def test_stale_lock_stolen(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    (vault / "meta").mkdir(parents=True)
    stale_pid = 999999  # very unlikely to be alive
    stale = {"pid": stale_pid, "ppid": 1, "role": "pm-loop", "start_ts": 0, "host": "x"}
    (vault / "meta" / ".lock.pm-loop").write_text(json.dumps(stale))

    lock = VaultLock(vault)
    lock.acquire()  # should steal
    held = json.loads(lock.lock_path.read_text())
    assert held["pid"] == os.getpid()
    lock.release()


def test_context_manager(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    with VaultLock(vault) as lock:
        assert lock.lock_path.exists()
    assert not lock.lock_path.exists()


def test_different_roles_independent(tmp_path: Path) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    a = VaultLock(vault, role="pm-loop")
    b = VaultLock(vault, role="audit")
    a.acquire()
    b.acquire()  # different role, should succeed
    assert a.lock_path != b.lock_path
    a.release()
    b.release()


def test_acquire_corrupt_lock_reports_error_type(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    vault = tmp_path / "v"
    (vault / "meta").mkdir(parents=True)
    (vault / "meta" / ".lock.pm-loop").write_text("{bad", encoding="utf-8")

    lock = VaultLock(vault)
    lock.acquire()

    err = capsys.readouterr().err
    assert "error_type=JSONDecodeError" in err
    lock.release()


def test_release_unexpected_lock_read_error_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault = tmp_path / "v"
    vault.mkdir()
    lock = VaultLock(vault)
    lock.acquire()
    original_read_text = Path.read_text

    def read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path == lock.lock_path:
            raise RuntimeError("unexpected")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)

    with pytest.raises(RuntimeError, match="unexpected"):
        lock.release()
