"""Phase 1 — Backup all existing Obsidian vaults to tarballs."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from ._base import Phase, PhaseResult
from ._mapping import VAULTS_TO_BACKUP


class BackupPhase(Phase):
    """Represent BackupPhase data for this module."""
    name = "1_backup"
    deps: list[str] = []

    def _backup_path(self, vault_name: str) -> Path:
        date = time.strftime("%Y%m%d-%H%M%S")
        return self.ctx.backup_dir / f"obsidian-backup-{vault_name}-{date}.tgz"

    def dry_run(self) -> str:
        out = ["[Phase 1] Would create:"]
        for v in VAULTS_TO_BACKUP:
            src = self.ctx.obsidian_root / v
            if src.is_dir():
                out.append(f"  tar czf {self._backup_path(v)} ← {src}")
        return "\n".join(out)

    def run(self) -> PhaseResult:
        self.ctx.backup_dir.mkdir(parents=True, exist_ok=True)
        created = []
        for v in VAULTS_TO_BACKUP:
            src = self.ctx.obsidian_root / v
            if not src.is_dir():
                self.ctx.trace(f"  skip backup (not present): {v}")
                continue
            tgt = self._backup_path(v)
            self.ctx.trace(f"  tar -> {tgt.name}")
            r = subprocess.run(
                ["tar", "czf", str(tgt), "-C", str(self.ctx.obsidian_root), v],
                capture_output=True, text=True, timeout=900,
            )
            if r.returncode != 0:
                return PhaseResult(status="failed", detail=f"tar failed for {v}: {r.stderr.strip()[:200]}")
            created.append(str(tgt))
        return PhaseResult(status="completed", detail=f"{len(created)} backups", artifacts={"backups": created})

    def verify(self) -> tuple[bool, str]:
        existing = list(self.ctx.backup_dir.glob("obsidian-backup-*.tgz"))
        if len(existing) < 1:
            return False, "no backup tarballs found"
        # Each tarball must be ≥1 KB (sanity)
        too_small = [p for p in existing if p.stat().st_size < 1024]
        if too_small:
            return False, f"tarballs too small: {[p.name for p in too_small]}"
        return True, f"{len(existing)} backup(s) present"

    def rollback(self) -> None:
        # Backup is itself the rollback artifact — never delete it on rollback.
        return
