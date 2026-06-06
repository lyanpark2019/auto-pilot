"""Phase 2 — Rename simple vaults to <project>-Vault convention.

Handles macOS case-insensitive filesystem via 2-step rename for case-only changes.
"""
from __future__ import annotations

import time
from pathlib import Path

from ._base import Phase, PhaseResult
from ._mapping import SIMPLE_RENAMES


def _case_only_change(old: str, new: str) -> bool:
    """True if old and new differ only in case (e.g., CLAI vs clai-Vault → False; PickL-Vault vs pickl-Vault → True)."""
    return old.lower() == new.lower() and old != new


def _entry_actual_name(parent: Path, name: str) -> str | None:
    """Return the actual filesystem name (case-preserved) matching `name` case-insensitively, or None."""
    if not parent.is_dir():
        return None
    needle = name.lower()
    for child in parent.iterdir():
        if child.name.lower() == needle:
            return child.name
    return None


class RenameSimplePhase(Phase):
    name = "2_rename_simple"
    deps = ["1_backup"]

    def _planned(self) -> list[tuple[str, str, str | None]]:
        """Return (old, new, actual_on_disk_or_None)."""
        out = []
        for old, new in SIMPLE_RENAMES.items():
            actual = _entry_actual_name(self.ctx.obsidian_root, old)
            # If `actual` already matches `new` (case-sensitive), nothing to do.
            out.append((old, new, actual))
        return out

    def dry_run(self) -> str:
        out = ["[Phase 2] Would rename:"]
        for old, new, actual in self._planned():
            if actual is None:
                out.append(f"  skip (not present): {old}")
            elif actual == new:
                out.append(f"  already renamed: {actual}")
            elif actual.lower() == new.lower():
                out.append(f"  case-only: {actual} → {new}  (uses 2-step rename)")
            else:
                out.append(f"  mv {actual} → {new}")
        return "\n".join(out)

    def _do_rename(self, actual: str, new: str) -> None:
        src = self.ctx.obsidian_root / actual
        dst = self.ctx.obsidian_root / new
        if actual == new:
            return
        if actual.lower() == new.lower():
            # case-only change — use intermediate name (case-insensitive FS)
            tmp_name = f"__rename_tmp_{int(time.time() * 1000)}"
            tmp = self.ctx.obsidian_root / tmp_name
            self.ctx.trace(f"  {actual} → {tmp_name} → {new}  (case-only via tmp)")
            src.rename(tmp)
            tmp.rename(dst)
        else:
            self.ctx.trace(f"  mv {actual} → {new}")
            src.rename(dst)

    def run(self) -> PhaseResult:
        renamed = []
        for old, new, actual in self._planned():
            if actual is None:
                self.ctx.trace(f"  skip (not present): {old}")
                continue
            if actual == new:
                self.ctx.trace(f"  skip (already renamed): {new}")
                continue
            self._do_rename(actual, new)
            renamed.append(f"{actual}→{new}")
        return PhaseResult(status="completed", detail=f"{len(renamed)} renamed", artifacts={"renamed": renamed})

    def verify(self) -> tuple[bool, str]:
        for old, new in SIMPLE_RENAMES.items():
            actual = _entry_actual_name(self.ctx.obsidian_root, new)
            if actual is None:
                # neither old nor new — was source ever present? skip
                continue
            if actual != new:
                return False, f"expected case '{new}', found '{actual}'"
        return True, "all simple renames done"

    def rollback(self) -> None:
        for old, new in SIMPLE_RENAMES.items():
            actual = _entry_actual_name(self.ctx.obsidian_root, new)
            if actual is None or actual != new:
                continue
            self.ctx.trace(f"  rollback: {actual} → {old}")
            self._do_rename(actual, old)
