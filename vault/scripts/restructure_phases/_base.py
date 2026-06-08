"""Base Phase class — uniform interface for the autonomous restructure loop."""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PhaseResult:
    """Represent PhaseResult data for this module."""
    status: str  # completed | failed | partial
    detail: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)


class Phase:
    """Subclass override: name, deps, run(), verify(), rollback()."""

    name: str = ""
    deps: list[str] = []  # other phase names that must be completed first

    def __init__(self, ctx: "PhaseContext"):
        self.ctx = ctx

    def dry_run(self) -> str:
        """Return human-readable description of what run() would do. No side effects."""
        return f"[{self.name}] (override dry_run)"

    def run(self) -> PhaseResult:
        raise NotImplementedError

    def verify(self) -> tuple[bool, str]:
        """Return (passed, reason). Called after run() to confirm success."""
        return True, "no verifier"

    def rollback(self) -> None:
        """Revert side effects. Best-effort."""
        return None


@dataclass
class PhaseContext:
    """Shared mutable context passed to every phase."""

    obsidian_root: Path
    project_root: Path
    plugin_root: Path
    state_path: Path
    backup_dir: Path
    dry_run_mode: bool = False
    execute_builds: bool = False  # Phase 6: actually shell-out to `claude -p /vault-build`
    only_domain: str | None = None  # Phase 6: restrict execution to this single domain
    log: list[str] = field(default_factory=list)

    def trace(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log.append(line)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
