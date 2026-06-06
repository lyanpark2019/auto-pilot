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

import errno
import fcntl
import hashlib
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, cast

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
    return atomic_write_text(path, json.dumps(c, indent=2, sort_keys=True) + "\n")


def read_contract(path: Path) -> dict[str, Any]:
    """Read + validate a contract from ``path``."""
    data = json.loads(path.read_text())
    validate(data)
    return cast(dict[str, Any], data)


def atomic_write_text(path: Path, text: str) -> Path:
    """Cross-platform atomic file write — tempfile + fsync + rename + dir fsync.

    Same-mount tempfile placed alongside target so ``os.replace`` is atomic
    on POSIX. ``F_FULLFSYNC`` used on Darwin (APFS); ``os.fsync`` elsewhere.
    Exposed for other private modules in this package (e.g. ``_state``).
    """
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
    fd = os.open(str(dir_path), os.O_RDONLY)
    try:
        _fsync_file(fd)
    finally:
        os.close(fd)


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


class SnapshotMismatchError(Exception):
    """Raised when context-bundle file SHAs do not match contract.snapshot_shas."""


@dataclass(frozen=True)
class SnapshotShas:
    spec: str
    claude_md_chain: list[str]
    project_context: str | None = None


def snapshot_context(dest_dir: Path, spec_path: Path,
                     claude_md_chain: list[Path],
                     project_context_path: Path | None = None) -> SnapshotShas:
    """Copy spec + CLAUDE chain (+ optional project_context) into
    <dest_dir>/context-bundle/, write MANIFEST, return sha256s of the copied bytes.

    If ``project_context_path`` is provided its bytes are copied as
    ``project-context.md`` and its sha is recorded in the returned
    :class:`SnapshotShas`.  Absent → ``project_context=None`` (context-blind run).
    """
    bundle = dest_dir / "context-bundle"
    bundle.mkdir(parents=True, exist_ok=True)

    spec_dest = bundle / "spec.md"
    shutil.copy2(spec_path, spec_dest)
    spec_sha = _sha256(spec_dest.read_bytes())

    chain_shas: list[str] = []
    manifest_lines = [f"{spec_sha}  spec.md"]
    for src in claude_md_chain:
        # Preserve folder-level naming: root CLAUDE.md vs CLAUDE-<sub>.md
        name = "CLAUDE.md" if src.name == "CLAUDE.md" and not chain_shas else f"CLAUDE-{src.parent.name}.md"
        if not chain_shas and src.name == "CLAUDE.md":
            name = "CLAUDE.md"
        dest = bundle / name
        shutil.copy2(src, dest)
        sha = _sha256(dest.read_bytes())
        chain_shas.append(sha)
        manifest_lines.append(f"{sha}  {name}")

    context_sha: str | None = None
    if project_context_path is not None:
        ctx_dest = bundle / "project-context.md"
        shutil.copy2(project_context_path, ctx_dest)
        context_sha = _sha256(ctx_dest.read_bytes())
        manifest_lines.append(f"{context_sha}  project-context.md")

    (bundle / "MANIFEST.txt").write_text("\n".join(manifest_lines) + "\n")
    return SnapshotShas(spec=spec_sha, claude_md_chain=chain_shas,
                        project_context=context_sha)


def verify_snapshots(contract_dir: Path) -> None:
    """Re-read context-bundle files, recompute SHAs, compare to contract.snapshot_shas.

    For ``project_context``:
      - Declared sha → bundle file ``project-context.md`` must exist + match
        (fail-closed: raises :class:`SnapshotMismatchError` on any mismatch).
      - Absent key → logs "ran context-blind" to stderr and continues (Step-1
        semantics: context-free runs are allowed but explicitly surfaced).

    Raises SnapshotMismatchError on any mismatch.
    """
    import sys as _sys
    contract = read_contract(contract_dir / "contract.json")
    bundle = Path(contract["context_bundle_path"])
    expected_spec = contract["snapshot_shas"]["spec"]
    actual_spec = _sha256((bundle / "spec.md").read_bytes())
    if actual_spec != expected_spec:
        raise SnapshotMismatchError(f"spec.md sha mismatch: {actual_spec!r} != {expected_spec!r}")

    expected_chain = contract["snapshot_shas"]["claude_md_chain"]
    # Discover bundle CLAUDE files in stable order: CLAUDE.md first, then CLAUDE-*.md sorted
    chain_files: list[Path] = []
    if (bundle / "CLAUDE.md").exists():
        chain_files.append(bundle / "CLAUDE.md")
    chain_files.extend(sorted(bundle.glob("CLAUDE-*.md")))
    actual_chain = [_sha256(p.read_bytes()) for p in chain_files]
    if actual_chain != expected_chain:
        raise SnapshotMismatchError(
            f"claude_md_chain sha mismatch: {actual_chain!r} != {expected_chain!r}"
        )

    expected_ctx = contract["snapshot_shas"].get("project_context")
    if expected_ctx is None:
        print("verify_snapshots: ran context-blind (no project_context sha declared)",
              file=_sys.stderr)
    else:
        ctx_file = bundle / "project-context.md"
        if not ctx_file.exists():
            raise SnapshotMismatchError(
                "project-context.md declared in snapshot_shas but absent from bundle"
            )
        actual_ctx = _sha256(ctx_file.read_bytes())
        if actual_ctx != expected_ctx:
            raise SnapshotMismatchError(
                f"project-context.md sha mismatch: {actual_ctx!r} != {expected_ctx!r}"
            )


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class PMSignatureMismatchError(Exception):
    """Raised when PM-SIGNATURE fails to match recomputed manifest/contract shas."""


def write_pm_signature(contract_dir: Path, run_id: str) -> Path:
    """Write <contract_dir>/PM-SIGNATURE binding the MANIFEST + contract.json shas to run_id."""
    manifest = contract_dir / "context-bundle" / "MANIFEST.txt"
    contract = contract_dir / "contract.json"
    sig = {
        "manifest_sha": _sha256(manifest.read_bytes()),
        "contract_sha": _sha256(contract.read_bytes()),
        "signed_at":    datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id":       run_id,
    }
    sig_path = contract_dir / "PM-SIGNATURE"
    return atomic_write_text(sig_path, json.dumps(sig, indent=2, sort_keys=True) + "\n")


def verify_pm_signature(contract_dir: Path) -> None:
    """Recompute MANIFEST + contract shas, compare to PM-SIGNATURE. Raise on mismatch."""
    sig_path = contract_dir / "PM-SIGNATURE"
    sig = json.loads(sig_path.read_text())
    manifest = contract_dir / "context-bundle" / "MANIFEST.txt"
    contract = contract_dir / "contract.json"
    actual_manifest = _sha256(manifest.read_bytes())
    actual_contract = _sha256(contract.read_bytes())
    if actual_manifest != sig["manifest_sha"]:
        raise PMSignatureMismatchError(f"manifest tampered: {actual_manifest} != {sig['manifest_sha']}")
    if actual_contract != sig["contract_sha"]:
        raise PMSignatureMismatchError(f"contract tampered: {actual_contract} != {sig['contract_sha']}")


def is_killed(contract_dir: Path) -> bool:
    """True if PM has touched <contract_dir>/CANCELED. Cheap to poll."""
    return (contract_dir / "CANCELED").exists()
