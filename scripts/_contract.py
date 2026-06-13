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
from typing import Iterator, cast

import jsonschema

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
CONTRACT_SCHEMA_PATH = SCHEMAS_DIR / "contract.schema.json"
_VALIDATOR: jsonschema.Draft202012Validator | None = None
JsonObject = dict[str, object]


def _as_str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise SnapshotMismatchError(f"expected string JSON value, got {type(value).__name__}")


def _as_object(value: object) -> JsonObject:
    if isinstance(value, dict):
        return cast(JsonObject, value)
    raise SnapshotMismatchError(f"expected object JSON value, got {type(value).__name__}")


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise SnapshotMismatchError(f"expected string-list JSON value, got {type(value).__name__}")


def _as_optional_str(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise SnapshotMismatchError(f"expected optional string JSON value, got {type(value).__name__}")


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


def validate(c: JsonObject) -> None:
    """Validate a contract dict against schemas/contract.schema.json.

    Raises:
        ContractValidationError on any violation; .args[0] is a human-readable summary.
    """
    errors = sorted(_validator().iter_errors(c), key=lambda e: e.path)
    if errors:
        msg = "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        raise ContractValidationError(msg)


def write_contract(c: JsonObject, path: Path) -> Path:
    """Atomic write of a validated contract to ``path``.

    Same-mount tempfile + fsync(fd) + rename + fsync(dir_fd). On Darwin uses
    F_FULLFSYNC. Returns the final path.
    """
    validate(c)
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_text(path, json.dumps(c, indent=2, sort_keys=True) + "\n")


def read_contract(path: Path) -> JsonObject:
    """Read + validate a contract from ``path``."""
    data = json.loads(path.read_text())
    validate(data)
    return cast(JsonObject, data)


def atomic_write_text(path: Path, text: str) -> Path:
    """Cross-platform atomic file write — tempfile + fsync + rename + dir fsync.

    Same-mount tempfile placed alongside target so ``os.replace`` is atomic
    on POSIX. ``F_FULLFSYNC`` used on Darwin (APFS); ``os.fsync`` elsewhere.
    Exposed for other private modules in this package (e.g. ``_state``).
    """
    # Same-fs tempfile in target dir
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    renamed = False
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            _fsync_file(f.fileno())
        os.replace(tmp_name, path)  # atomic on same fs
        renamed = True
        _fsync_dir(path.parent)
    finally:
        if not renamed:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
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
    """Represent SnapshotShas data for this module."""
    spec: str
    claude_md_chain: list[str]
    project_context: str | None = None


_CHAIN_PREFIX = "CLAUDE-chain-"


def _chain_bundle_name(idx: int, src: Path) -> str:
    """Order-preserving, collision-proof bundle filename for a CLAUDE chain entry.

    Zero-padded index keeps ``sorted()`` in chain order; index disambiguates
    same-leaf-name dirs (e.g. src/api vs lib/api) so copies never overwrite.
    """
    label = "root" if idx == 0 else src.parent.name
    return f"{_CHAIN_PREFIX}{idx:02d}-{label}.md"


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
    for idx, src in enumerate(claude_md_chain):
        name = _chain_bundle_name(idx, src)
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


def _verify_spec_sha(bundle: Path, expected_spec: str) -> None:
    actual_spec = _sha256((bundle / "spec.md").read_bytes())
    if actual_spec != expected_spec:
        raise SnapshotMismatchError(f"spec.md sha mismatch: {actual_spec!r} != {expected_spec!r}")


def _bundle_claude_files(bundle: Path) -> list[Path]:
    return sorted(bundle.glob(f"{_CHAIN_PREFIX}*.md"))


def _verify_claude_chain(bundle: Path, expected_chain: list[str]) -> None:
    actual_chain = [_sha256(p.read_bytes()) for p in _bundle_claude_files(bundle)]
    if actual_chain != expected_chain:
        raise SnapshotMismatchError(
            f"claude_md_chain sha mismatch: {actual_chain!r} != {expected_chain!r}"
        )


def _verify_project_context(bundle: Path, expected_ctx: str | None) -> None:
    if expected_ctx is None:
        sys.stderr.write("verify_snapshots: ran context-blind (no project_context sha declared)\n")
        return
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


def verify_snapshots(contract_dir: Path) -> None:
    """Re-read context-bundle files, recompute SHAs, compare to contract.snapshot_shas."""
    contract = read_contract(contract_dir / "contract.json")
    bundle = Path(_as_str(contract["context_bundle_path"]))
    snapshot_shas = _as_object(contract["snapshot_shas"])
    _verify_spec_sha(bundle, _as_str(snapshot_shas["spec"]))
    _verify_claude_chain(bundle, _as_str_list(snapshot_shas["claude_md_chain"]))
    _verify_project_context(bundle, _as_optional_str(snapshot_shas.get("project_context")))


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
