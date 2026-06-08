"""Phase 3 — Merge Sportic/ + SporTic365/ → sportic365-Vault/."""
from __future__ import annotations

import shutil
from pathlib import Path

from ._base import Phase, PhaseResult
from ._mapping import SPORTIC_SUB_DIRS


class Sportic365MergePhase(Phase):
    name = "3_sportic365_merge"
    deps = ["2_rename_simple"]

    @property
    def target(self) -> Path:
        return self.ctx.obsidian_root / "sportic365-Vault"

    def dry_run(self) -> str:
        out = ["[Phase 3] sportic365 merge plan:"]
        sportic = self.ctx.obsidian_root / "Sportic"
        sportic365 = self.ctx.obsidian_root / "SporTic365"
        out.append(f"  mkdir {self.target}/{{_sub-projects,_legacy,kbo-reference,meta}}")
        if sportic365.is_dir():
            out.append(f"  mv {sportic365} → {self.target}/_sub-projects/sportic365-content")
        if sportic.is_dir():
            for sub in SPORTIC_SUB_DIRS:
                src = sportic / sub
                if src.is_dir():
                    out.append(f"  mv {src} → {self.target}/_sub-projects/{sub}")
            wiki = sportic / "wiki"
            if wiki.is_dir():
                out.append(f"  mv {wiki} → {self.target}/kbo-reference")
            out.append(f"  mv {sportic}/* → {self.target}/_legacy/   (catch-all root jumble)")
            out.append(f"  rmdir {sportic}")
        return "\n".join(out)

    def _ensure_skeleton(self) -> None:
        for sub in ["_sub-projects", "_legacy", "kbo-reference", "meta"]:
            (self.target / sub).mkdir(parents=True, exist_ok=True)

    def _move_sportic365(self, sportic365: Path, moved: list[str]) -> None:
        if not sportic365.is_dir():
            return
        dst = self.target / "_sub-projects" / "sportic365-content"
        if dst.exists():
            self.ctx.trace(f"  skip (target exists): {dst}")
            return
        self.ctx.trace("  mv SporTic365 → _sub-projects/sportic365-content")
        shutil.move(str(sportic365), str(dst))
        moved.append("SporTic365→_sub-projects/sportic365-content")

    def _move_sportic_subdirs(self, sportic: Path, moved: list[str]) -> None:
        for sub in SPORTIC_SUB_DIRS:
            src = sportic / sub
            if not src.is_dir():
                continue
            dst = self.target / "_sub-projects" / sub
            if dst.exists():
                self.ctx.trace(f"  skip (exists): _sub-projects/{sub}")
                continue
            self.ctx.trace(f"  mv Sportic/{sub} → _sub-projects/{sub}")
            shutil.move(str(src), str(dst))
            moved.append(f"Sportic/{sub}→_sub-projects/{sub}")

    def _move_wiki(self, sportic: Path, moved: list[str]) -> None:
        wiki_src = sportic / "wiki"
        wiki_dst = self.target / "kbo-reference"
        if not wiki_src.is_dir():
            return
        if any(wiki_dst.iterdir()):
            self.ctx.trace("  skip wiki (kbo-reference non-empty)")
            return
        self.ctx.trace("  mv Sportic/wiki/* → kbo-reference/")
        for child in list(wiki_src.iterdir()):
            shutil.move(str(child), str(wiki_dst / child.name))
        wiki_src.rmdir()
        moved.append("Sportic/wiki→kbo-reference")

    def _move_remaining_to_legacy(self, sportic: Path) -> None:
        legacy_dst = self.target / "_legacy"
        for child in list(sportic.iterdir()):
            tgt = legacy_dst / child.name
            if tgt.exists():
                continue
            self.ctx.trace(f"  mv Sportic/{child.name} → _legacy/")
            shutil.move(str(child), str(tgt))

    def _remove_sportic(self, sportic: Path, moved: list[str]) -> None:
        try:
            sportic.rmdir()
            moved.append("rmdir Sportic")
        except OSError:
            self.ctx.trace("  Sportic not empty after move — leaving in place")

    def run(self) -> PhaseResult:
        self._ensure_skeleton()
        sportic = self.ctx.obsidian_root / "Sportic"
        sportic365 = self.ctx.obsidian_root / "SporTic365"
        moved: list[str] = []
        self._move_sportic365(sportic365, moved)
        if sportic.is_dir():
            self._move_sportic_subdirs(sportic, moved)
            self._move_wiki(sportic, moved)
            self._move_remaining_to_legacy(sportic)
            self._remove_sportic(sportic, moved)
        return PhaseResult(status="completed", detail=f"{len(moved)} ops", artifacts={"moves": moved})

    def verify(self) -> tuple[bool, str]:
        if not self.target.is_dir():
            return False, "sportic365-Vault missing"
        # Either _sub-projects has at least one entry or both sources are gone
        sportic = self.ctx.obsidian_root / "Sportic"
        sportic365 = self.ctx.obsidian_root / "SporTic365"
        if sportic.is_dir() or sportic365.is_dir():
            return False, "old Sportic / SporTic365 still present"
        sub_proj = self.target / "_sub-projects"
        if not sub_proj.is_dir() or not any(sub_proj.iterdir()):
            return False, "_sub-projects empty"
        return True, "merge verified"

    def rollback(self) -> None:
        # Best-effort: just log. Real recovery is via tarballs.
        self.ctx.trace("  Phase 3 rollback: restore from /tmp/obsidian-backup-Sportic*.tgz manually")
