"""On-disk contract layer for auto-pilot.

Single source of truth for the contract.json schema, atomic IO, file locking,
context-bundle snapshotting, and PM-SIGNATURE chain.

Locking model:
  - per-contract dir lock `.lock` — fcntl.LOCK_EX for writers, LOCK_SH for readers
  - all writes: tempfile (same fs) → fsync(fd) → atomic rename → fsync(dir_fd)

FS requirements: local fs only (NFS rejected; see assert_local_fs()).
Platform-specific durability:
  - Darwin (macOS APFS): use fcntl.fcntl(fd, F_FULLFSYNC) instead of os.fsync().
    APFS does not guarantee that os.fsync() flushes to physical media; only
    F_FULLFSYNC does. Detection: sys.platform == "darwin". EINTR retry bounded.
  - Linux (ext4/xfs/btrfs): os.fsync() suffices.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
CONTRACT_SCHEMA_PATH = SCHEMAS_DIR / "contract.schema.json"
_VALIDATOR: jsonschema.Draft202012Validator | None = None


class ContractValidationError(Exception):
    """Raised when a contract dict fails schema validation."""


def _validator() -> jsonschema.Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = json.loads(CONTRACT_SCHEMA_PATH.read_text())
        _VALIDATOR = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
    return _VALIDATOR


def validate(c: dict[str, Any]) -> None:
    """Validate a contract dict against schemas/contract.schema.json.

    Raises:
        ContractValidationError on any violation; .args[0] is a human-readable summary.
    """
    errors = sorted(_validator().iter_errors(c), key=lambda e: e.path)
    if errors:
        msg = "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        raise ContractValidationError(msg)


def write_contract(c: dict[str, Any], path: Path) -> Path:
    """Atomic write of a validated contract to ``path``.

    Same-mount tempfile + fsync(fd) + rename + fsync(dir_fd). On Darwin uses
    F_FULLFSYNC. Returns the final path.
    """
    validate(c)
    path.parent.mkdir(parents=True, exist_ok=True)
    return _atomic_write_text(path, json.dumps(c, indent=2, sort_keys=True) + "\n")


def read_contract(path: Path) -> dict[str, Any]:
    """Read + validate a contract from ``path``."""
    data = json.loads(path.read_text())
    validate(data)
    return data


def _atomic_write_text(path: Path, text: str) -> Path:
    import os
    import tempfile
    # Same-fs tempfile in target dir
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            _fsync_file(f.fileno())
        os.replace(tmp_name, path)  # atomic on same fs
        _fsync_dir(path.parent)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return path


def _fsync_file(fd: int) -> None:
    import errno
    import fcntl
    import os
    if sys.platform == "darwin":
        for _ in range(5):
            try:
                fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
                return
            except InterruptedError:
                continue
            except OSError as e:
                if e.errno == errno.EINTR:
                    continue
                raise
        # last resort
        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)


def _fsync_dir(dir_path: Path) -> None:
    import os
    fd = os.open(str(dir_path), os.O_RDONLY)
    try:
        _fsync_file(fd)
    finally:
        os.close(fd)


import fcntl
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def write_lock(dir_path: Path) -> Iterator[None]:
    """Exclusive lock on `<dir_path>/.lock`. Blocks until acquired."""
    dir_path.mkdir(parents=True, exist_ok=True)
    lock_path = dir_path / ".lock"
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


@contextmanager
def read_lock(dir_path: Path) -> Iterator[None]:
    """Shared lock on `<dir_path>/.lock`. Blocks until acquired."""
    dir_path.mkdir(parents=True, exist_ok=True)
    lock_path = dir_path / ".lock"
    lock_path.touch(exist_ok=True)
    fd = lock_path.open("r")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_SH)
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        finally:
            fd.close()
