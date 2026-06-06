"""Phase 5 — Create skeleton directories for vaults that don't yet exist."""
from __future__ import annotations

import time
from pathlib import Path

from ._base import Phase, PhaseResult
from ._mapping import DOMAINS


_INDEX_TEMPLATE = """---
type: index
domain: {domain}
created: {date}
auto_generated_by: vault-restructure
---

# {vault_name}

Domain vault for **{domain}**.

## Sub-projects

{sub_list}

## Subdirs

- `_sub-projects/` — per-project documentation (vault-builder will populate)
- `notebooklm-archive/` — frozen NotebookLM source pages (where applicable)
- `meta/` — vault-builder state (score-state.json, ticket-state.json, etc.)

Run `/vault-build <repo> --obsidian-path <vault>` to populate from code.
"""


class NewVaultSkeletonsPhase(Phase):
    name = "5_new_vault_skeletons"
    deps = ["4_notebooklm_split"]

    def _planned_vaults(self) -> list[tuple[str, Path]]:
        out = []
        for domain, info in DOMAINS.items():
            vault = self.ctx.obsidian_root / info["vault"]
            out.append((domain, vault))
        return out

    def dry_run(self) -> str:
        lines = ["[Phase 5] Skeleton creation:"]
        for domain, vault in self._planned_vaults():
            if vault.is_dir():
                lines.append(f"  exists, ensure subdirs: {vault.name}")
            else:
                lines.append(f"  mkdir {vault.name}/{{_sub-projects,meta}}")
            lines.append(f"  write {vault.name}/_index.md")
        return "\n".join(lines)

    def run(self) -> PhaseResult:
        created = []
        for domain, vault in self._planned_vaults():
            vault.mkdir(parents=True, exist_ok=True)
            for sub in ["_sub-projects", "meta"]:
                (vault / sub).mkdir(parents=True, exist_ok=True)
            # _index.md (idempotent — only write if absent)
            idx = vault / "_index.md"
            info = DOMAINS[domain]
            if not idx.exists():
                sub_list = "\n".join(f"- `{p}`" for p in info["sub_projects"])
                idx.write_text(
                    _INDEX_TEMPLATE.format(
                        domain=domain,
                        vault_name=vault.name,
                        date=time.strftime("%Y-%m-%d"),
                        sub_list=sub_list,
                    )
                )
                created.append(f"{vault.name}/_index.md")
        return PhaseResult(status="completed", detail=f"{len(created)} index files created", artifacts={"new_files": created})

    def verify(self) -> tuple[bool, str]:
        for domain, vault in self._planned_vaults():
            if not vault.is_dir():
                return False, f"missing vault: {vault.name}"
            if not (vault / "meta").is_dir():
                return False, f"missing meta/: {vault.name}"
            if not (vault / "_sub-projects").is_dir():
                return False, f"missing _sub-projects/: {vault.name}"
        return True, "all skeletons present"

    def rollback(self) -> None:
        # Skeletons are non-destructive — leave them.
        return
