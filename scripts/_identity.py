"""Neutral identity/path utilities shared across ledger-backed subsystems.

These were originally part of the learning-loop modules (since removed), but
they are generic — plugin version, repo slug / fingerprint, a ledger flock, and
vault-path resolution — and consumed by the escalation and enrichment
subsystems. Homed here so those subsystems carry no learning-loop dependency.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def _read_plugin_version() -> str:
    here = Path(__file__).resolve()
    for parent in here.parents:
        manifest = parent / ".claude-plugin" / "plugin.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
            except (OSError, json.JSONDecodeError):
                return "0"
            version = data.get("version")
            return version if isinstance(version, str) else "0"
    return "0"


PLUGIN_VERSION: str = _read_plugin_version()


def project_slug(repo_root: Path) -> str:
    """``~/.claude/projects/<slug>`` style slug for a repo root."""
    return str(repo_root.resolve()).replace("/", "-")


def repo_fingerprint(repo_root: Path) -> str:
    """Stable 16-char id of the target repo — git remote URL, else abspath."""
    seed = str(repo_root.resolve())
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            seed = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


@contextmanager
def ledger_lock(lock_path: Path) -> Iterator[None]:
    """Exclusive flock on ``<fp>.json.lock``, held across the read-modify-write."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
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


def resolve_vault(repo_root: Path) -> Path:
    """Resolve vault path using the standard precedence.

    Order: ``NBM_VAULT_PATH`` → ``VAULT_BUILDER_VAULT`` →
    ``${VB_OBSIDIAN_ROOT:-$HOME/Documents/Obsidian}/<basename(repo_root)>``.
    Mirrors ``hooks/session-distill-stop.sh`` resolution exactly.
    """
    vault_str = os.environ.get("NBM_VAULT_PATH") or os.environ.get("VAULT_BUILDER_VAULT") or ""
    if vault_str:
        return Path(vault_str)
    obsidian_root = Path(
        os.environ.get("VB_OBSIDIAN_ROOT")
        or str(Path.home() / "Documents" / "Obsidian")
    )
    return obsidian_root / repo_root.name
