#!/usr/bin/env python3
"""Per-vault lockfile: prevent concurrent PM loops on the same vault.

Usage:
    from lockfile import VaultLock
    with VaultLock(vault_path) as lock:
        # PM loop runs here; lock auto-released on exit/crash
        ...

Lockfile stores pid + start_ts. If existing lock holds a dead pid, it's stolen.
If pid alive, raises LockHeldError with held-by info.
"""
from __future__ import annotations

import errno
import json
import os
import sys
import time
from pathlib import Path
from typing import TextIO


class LockHeldError(RuntimeError):
    pass


def _write_line(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")


def _warn(message: str) -> None:
    _write_line(sys.stderr, message)


def _emit_json(payload: object, *, stream: TextIO = sys.stdout) -> None:
    _write_line(stream, json.dumps(payload))


def _load_lock(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _pid_from_lock(held: dict[str, object]) -> int | None:
    pid = held.get("pid")
    return pid if isinstance(pid, int) else None


class VaultLock:
    def __init__(self, vault: Path, role: str = "pm-loop"):
        self.vault = Path(vault).expanduser().resolve()
        self.role = role
        self.lock_path = self.vault / "meta" / f".lock.{role}"
        self._acquired = False

    def __enter__(self) -> VaultLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                held = _load_lock(self.lock_path)
            except (OSError, json.JSONDecodeError) as exc:
                _warn(
                    f"lockfile: corrupt lock file {self.lock_path}: "
                    f"error_type={type(exc).__name__}: {exc}"
                )
                held = {}
            held_pid = _pid_from_lock(held)
            if held_pid is not None and self._pid_alive(held_pid):
                raise LockHeldError(
                    f"Vault {self.vault.name} {self.role} lock held by pid {held_pid} "
                    f"since {held.get('start_ts')} (host {held.get('host','?')})"
                )
            # Stale lock — steal it
            self._write_lock()
            self._acquired = True
            return
        self._write_lock()
        self._acquired = True

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            held = _load_lock(self.lock_path)
            if held.get("pid") == os.getpid():
                self.lock_path.unlink()
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            _warn(
                f"lockfile: release skipped for {self.lock_path}: "
                f"error_type={type(exc).__name__}: {exc}"
            )
        self._acquired = False

    def _write_lock(self) -> None:
        payload = {
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "role": self.role,
            "start_ts": time.time(),
            "host": os.uname().nodename if hasattr(os, "uname") else "unknown",
        }
        self.lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError as e:
            return e.errno == errno.EPERM


def _release_existing_lock(lock: VaultLock) -> int:
    try:
        held = _load_lock(lock.lock_path)
        held_pid = _pid_from_lock(held)
        if held_pid is None or held_pid == os.getpid() or not lock._pid_alive(held_pid):
            lock.lock_path.unlink()
            _emit_json({"released": True})
            return 0
        _emit_json({"released": False, "reason": "held by live pid"}, stream=sys.stderr)
        return 3
    except (OSError, json.JSONDecodeError) as exc:
        _emit_json(
            {"released": False, "error": str(exc), "error_type": type(exc).__name__},
            stream=sys.stderr,
        )
        return 1


def _status(lock: VaultLock) -> int:
    if lock.lock_path.exists():
        try:
            _write_line(sys.stdout, lock.lock_path.read_text(encoding="utf-8"))
        except OSError as exc:
            _emit_json({"error": str(exc), "error_type": type(exc).__name__})
    else:
        _emit_json({"locked": False})
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        _write_line(sys.stderr, "usage: lockfile.py <vault> {acquire|release|status} [role]")
        return 1
    vault = Path(argv[1])
    cmd = argv[2]
    role = argv[3] if len(argv) > 3 else "pm-loop"
    lock = VaultLock(vault, role)

    if cmd == "acquire":
        try:
            lock.acquire()
            _emit_json({"acquired": True, "path": str(lock.lock_path)})
            return 0
        except LockHeldError as e:
            _emit_json({"acquired": False, "error": str(e)}, stream=sys.stderr)
            return 2
    if cmd == "release":
        if lock.lock_path.exists():
            return _release_existing_lock(lock)
        _emit_json({"released": True, "note": "no lock"})
        return 0
    if cmd == "status":
        return _status(lock)
    _write_line(sys.stderr, f"unknown cmd: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
