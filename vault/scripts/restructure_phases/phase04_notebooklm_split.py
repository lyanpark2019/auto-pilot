"""Phase 4 — Split NotebookLM-Archive categories into per-domain vaults."""
from __future__ import annotations

import shutil
from pathlib import Path

from ._base import Phase, PhaseResult
from ._mapping import DOMAINS, NBM_GENERIC_KEEP


class NotebookLMSplitPhase(Phase):
    """Represent NotebookLMSplitPhase data for this module."""
    name = "4_notebooklm_split"
    deps = ["3_sportic365_merge"]

    @property
    def archive(self) -> Path:
        return self.ctx.obsidian_root / "NotebookLM-Archive"

    def _moves(self) -> list[tuple[Path, Path]]:
        moves = []
        for domain, info in DOMAINS.items():
            cats = info.get("notebooklm_cats_absorb", [])
            if not cats:
                continue
            dst_vault = self.ctx.obsidian_root / info["vault"]
            for cat in cats:
                src = self.archive / cat
                if not src.is_dir():
                    continue
                # All absorbed cats land under <vault>/notebooklm-archive/<cat>
                dst = dst_vault / "notebooklm-archive" / cat
                moves.append((src, dst))
        return moves

    def dry_run(self) -> str:
        out = ["[Phase 4] NotebookLM-Archive split:"]
        for src, dst in self._moves():
            out.append(f"  mv {src} → {dst}")
        out.append(f"  keep in NotebookLM-Archive: {', '.join(NBM_GENERIC_KEEP)}")
        return "\n".join(out)

    def run(self) -> PhaseResult:
        moved = []
        for src, dst in self._moves():
            if not src.is_dir():
                continue
            if dst.exists():
                self.ctx.trace(f"  skip (exists): {dst}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            self.ctx.trace(f"  mv {src.name} → {dst.relative_to(self.ctx.obsidian_root)}")
            shutil.move(str(src), str(dst))
            moved.append(f"{src.name}→{dst.relative_to(self.ctx.obsidian_root)}")
        return PhaseResult(status="completed", detail=f"{len(moved)} categories moved", artifacts={"moves": moved})

    def verify(self) -> tuple[bool, str]:
        # All listed cats should be gone from NBM-Archive
        for domain, info in DOMAINS.items():
            for cat in info.get("notebooklm_cats_absorb", []):
                src = self.archive / cat
                if src.is_dir():
                    return False, f"category still in archive: {cat}"
        # generic cats still present
        for keep in NBM_GENERIC_KEEP:
            if not (self.archive / keep).is_dir():
                self.ctx.trace(f"  warn: generic category absent: {keep} (was it ever there?)")
        return True, "split verified"

    def rollback(self) -> None:
        self.ctx.trace("  Phase 4 rollback: restore from /tmp/obsidian-backup-NotebookLM-Archive*.tgz")
