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

    def run(self) -> PhaseResult:
        # Idempotent: each sub-step guards with `if dst.exists(): skip`.
        # 1. Skeleton
        for sub in ["_sub-projects", "_legacy", "kbo-reference", "meta"]:
            (self.target / sub).mkdir(parents=True, exist_ok=True)

        sportic = self.ctx.obsidian_root / "Sportic"
        sportic365 = self.ctx.obsidian_root / "SporTic365"

        moved = []

        # 2. SporTic365 → _sub-projects/sportic365-content
        if sportic365.is_dir():
            dst = self.target / "_sub-projects" / "sportic365-content"
            if dst.exists():
                self.ctx.trace(f"  skip (target exists): {dst}")
            else:
                self.ctx.trace(f"  mv SporTic365 → _sub-projects/sportic365-content")
                shutil.move(str(sportic365), str(dst))
                moved.append("SporTic365→_sub-projects/sportic365-content")

        # 3. Sportic sub-vaults → _sub-projects/<name>
        if sportic.is_dir():
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

            # 4. wiki → kbo-reference (only if dst empty)
            wiki_src = sportic / "wiki"
            wiki_dst = self.target / "kbo-reference"
            if wiki_src.is_dir():
                if any(wiki_dst.iterdir()):
                    self.ctx.trace(f"  skip wiki (kbo-reference non-empty)")
                else:
                    self.ctx.trace(f"  mv Sportic/wiki/* → kbo-reference/")
                    for child in list(wiki_src.iterdir()):
                        shutil.move(str(child), str(wiki_dst / child.name))
                    wiki_src.rmdir()
                    moved.append("Sportic/wiki→kbo-reference")

            # 5. Remaining root contents → _legacy
            legacy_dst = self.target / "_legacy"
            for child in list(sportic.iterdir()):
                # Don't pull .obsidian — it's vault-specific config; preserve as legacy reference too
                tgt = legacy_dst / child.name
                if tgt.exists():
                    continue
                self.ctx.trace(f"  mv Sportic/{child.name} → _legacy/")
                shutil.move(str(child), str(tgt))
            # 6. Remove empty Sportic dir
            try:
                sportic.rmdir()
                moved.append("rmdir Sportic")
            except OSError:
                self.ctx.trace(f"  Sportic not empty after move — leaving in place")

        return PhaseResult(status="completed", detail=f"{len(moved)} ops", artifacts={"moves": moved})

    def verify(self) -> tuple[bool, str]:
        if not self.target.is_dir():
            return False, f"sportic365-Vault missing"
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
