"""Phase 8 — Post-restructure cleanup.

Idempotent. Removes empty cruft directories, moves misplaced files
discovered after the main restructure, and produces a cleanup report.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ._base import Phase, PhaseResult


# Always-empty cruft to delete if confirmed empty.
EMPTY_DIRS_TO_DELETE = [
    "sportic365-Vault/_legacy/EC2",
    "sportic365-Vault/_legacy/Sportic365",
    "NotebookLM-Archive/pickl-crosslink",
    "NotebookLM-Archive/sportic-dev-crosslink",
    "NotebookLM-Archive/archive-candidates",
]

# Misplaced files/dirs in _legacy that belong in domain vaults.
RELOCATIONS: list[dict[str, str]] = [
    {
        "from": "sportic365-Vault/_legacy/Sportic/프로토.md",
        "to": "proto-Vault/proto.md",
        "kind": "file",
    },
    {
        "from": "sportic365-Vault/_legacy/Sportic/Proto Analysis.md",
        "to": "proto-Vault/Proto Analysis.md",
        "kind": "file",
    },
    {
        "from": "sportic365-Vault/_legacy/Sportic/PickL-API",
        "to": "pickl-Vault/_sub-projects/PickL-API-legacy",
        "kind": "dir",
    },
]


class CleanupPhase(Phase):
    """Represent CleanupPhase data for this module."""
    name = "8_cleanup"
    deps = ["7_notebooklm_create"]

    def _is_truly_empty(self, p: Path) -> bool:
        if not p.is_dir():
            return False
        for child in p.iterdir():
            if child.name in (".DS_Store",):
                continue
            return False
        return True

    def dry_run(self) -> str:
        out = ["[Phase 8] Cleanup plan:"]
        for rel in EMPTY_DIRS_TO_DELETE:
            p = self.ctx.obsidian_root / rel
            if not p.is_dir():
                out.append(f"  skip (absent): {rel}")
            elif self._is_truly_empty(p):
                out.append(f"  rmdir {rel}")
            else:
                out.append(f"  skip (non-empty): {rel}")
        for r in RELOCATIONS:
            src = self.ctx.obsidian_root / r["from"]
            dst = self.ctx.obsidian_root / r["to"]
            if not src.exists():
                out.append(f"  skip (absent): {r['from']}")
            elif dst.exists():
                out.append(f"  skip (target exists): {r['to']}")
            else:
                out.append(f"  mv {r['from']} → {r['to']}")
        return "\n".join(out)

    def run(self) -> PhaseResult:
        deleted = []
        moved = []

        for rel in EMPTY_DIRS_TO_DELETE:
            p = self.ctx.obsidian_root / rel
            if not p.is_dir():
                continue
            if not self._is_truly_empty(p):
                self.ctx.trace(f"  skip (non-empty): {rel}")
                continue
            # remove .DS_Store first (only file we tolerate inside "empty")
            for child in list(p.iterdir()):
                if child.name == ".DS_Store":
                    child.unlink()
            try:
                p.rmdir()
                deleted.append(rel)
                self.ctx.trace(f"  rmdir {rel}")
            except OSError as e:
                self.ctx.trace(f"  rmdir failed: {rel} ({e})")

        for r in RELOCATIONS:
            src = self.ctx.obsidian_root / r["from"]
            dst = self.ctx.obsidian_root / r["to"]
            if not src.exists():
                continue
            if dst.exists():
                self.ctx.trace(f"  skip (target exists): {r['to']}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            self.ctx.trace(f"  mv {r['from']} → {r['to']}")
            shutil.move(str(src), str(dst))
            moved.append(f"{r['from']}→{r['to']}")

        return PhaseResult(
            status="completed",
            detail=f"{len(deleted)} dirs deleted, {len(moved)} files relocated",
            artifacts={"deleted": deleted, "moved": moved},
        )

    def verify(self) -> tuple[bool, str]:
        # Soft verify: previously-targeted empty dirs should be gone OR still non-empty
        for rel in EMPTY_DIRS_TO_DELETE:
            p = self.ctx.obsidian_root / rel
            if p.is_dir() and self._is_truly_empty(p):
                return False, f"empty dir not deleted: {rel}"
        return True, "cleanup verified"

    def rollback(self) -> None:
        # Cleanup deletes empty dirs only — recreate via mkdir if needed.
        for rel in EMPTY_DIRS_TO_DELETE:
            p = self.ctx.obsidian_root / rel
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                self.ctx.trace(f"  rollback: mkdir {rel}")
