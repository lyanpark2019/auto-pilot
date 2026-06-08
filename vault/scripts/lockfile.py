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


class LockHeldError(RuntimeError):
    pass


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
                held = json.loads(self.lock_path.read_text())
            except Exception as exc:
                print(f"lockfile: corrupt lock file {self.lock_path}: {type(exc).__name__}: {exc}", file=sys.stderr)
                held = {}
            held_pid = held.get("pid")
            if held_pid and self._pid_alive(held_pid):
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
            held = json.loads(self.lock_path.read_text())
            if held.get("pid") == os.getpid():
                self.lock_path.unlink()
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"lockfile: release skipped for {self.lock_path}: {type(exc).__name__}: {exc}", file=sys.stderr)
        self._acquired = False

    def _write_lock(self) -> None:
        payload = {
            "pid": os.getpid(),
            "ppid": os.getppid(),
            "role": self.role,
            "start_ts": time.time(),
            "host": os.uname().nodename if hasattr(os, "uname") else "unknown",
        }
        self.lock_path.write_text(json.dumps(payload, indent=2))

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError as e:
            return e.errno == errno.EPERM


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: lockfile.py <vault> {acquire|release|status} [role]", file=sys.stderr)
        return 1
    vault = Path(argv[1])
    cmd = argv[2]
    role = argv[3] if len(argv) > 3 else "pm-loop"
    lock = VaultLock(vault, role)

    if cmd == "acquire":
        try:
            lock.acquire()
            print(json.dumps({"acquired": True, "path": str(lock.lock_path)}))
            return 0
        except LockHeldError as e:
            print(json.dumps({"acquired": False, "error": str(e)}), file=sys.stderr)
            return 2
    if cmd == "release":
        # Force-release: only if our pid or stale
        if lock.lock_path.exists():
            try:
                held = json.loads(lock.lock_path.read_text())
                if held.get("pid") == os.getpid() or not lock._pid_alive(held.get("pid", -1)):
                    lock.lock_path.unlink()
                    print(json.dumps({"released": True}))
                    return 0
                print(json.dumps({"released": False, "reason": "held by live pid"}), file=sys.stderr)
                return 3
            except Exception as e:
                print(json.dumps({"released": False, "error": str(e)}), file=sys.stderr)
                return 1
        print(json.dumps({"released": True, "note": "no lock"}))
        return 0
    if cmd == "status":
        if lock.lock_path.exists():
            try:
                print(lock.lock_path.read_text())
            except Exception as e:
                print(json.dumps({"error": str(e)}))
        else:
            print(json.dumps({"locked": False}))
        return 0
    print(f"unknown cmd: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
