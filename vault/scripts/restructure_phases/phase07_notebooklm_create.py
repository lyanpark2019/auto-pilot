"""Phase 7 — Create live NotebookLM notebooks per domain.

Like Phase 6, this emits a manifest. Actual `notebooklm create` invocation
requires authenticated CLI access; we emit the commands and let the autonomous
loop driver shell them out (or ask the user to run them).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ._base import Phase, PhaseResult
from ._mapping import NBM_NEW_NOTEBOOKS


class NotebookLMCreatePhase(Phase):
    """Represent NotebookLMCreatePhase data for this module."""
    name = "7_notebooklm_create"
    deps = ["6_vault_build_per_domain"]

    def _existing_notebooks(self) -> set[str]:
        """Query notebooklm CLI for current notebook titles. Returns title set."""
        nb_bin = shutil.which("notebooklm")
        if not nb_bin:
            return set()
        try:
            r = subprocess.run([nb_bin, "list", "--json"], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                return set()
            payload = json.loads(r.stdout) if r.stdout.strip() else {}
            return self._notebook_titles(payload)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, AttributeError, TypeError) as exc:
            sys.stderr.write(f"phase07: _existing_notebooks query failed: {type(exc).__name__}: {exc}\n")
            return set()

    def _notebook_titles(self, payload: Any) -> set[str]:
        if isinstance(payload, dict):
            notebooks = payload.get("notebooks", [])
        elif isinstance(payload, list):
            notebooks = payload
        else:
            notebooks = []
        return {nb.get("title", nb.get("name", "")) for nb in notebooks if isinstance(nb, dict)}

    def _planned_notebooks(self) -> list[dict]:
        out = []
        for domain, notebooks in NBM_NEW_NOTEBOOKS.items():
            for nb in notebooks:
                out.append({
                    "domain": domain,
                    "name": nb["name"],
                    "topic": nb["topic"],
                    "command": f'notebooklm create "{nb["name"]}"',
                })
        return out

    def dry_run(self) -> str:
        existing = self._existing_notebooks()
        out = ["[Phase 7] NotebookLM live notebooks:"]
        for nb in self._planned_notebooks():
            mark = "✓ exists" if nb["name"] in existing else "→ create"
            out.append(f"  {mark}  {nb['domain']:14s} {nb['name']}  ({nb['topic']})")
        return "\n".join(out)

    def _write_manifest(self, planned: list[dict], existing: set[str]) -> tuple[Path, list[dict]]:
        manifest_path = self.ctx.state_path.parent / "obsidian-restructure-notebooklm-manifest.json"
        manifest = [{**nb, "already_exists": nb["name"] in existing} for nb in planned]
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        self.ctx.trace(f"  notebooklm manifest → {manifest_path}")
        return manifest_path, manifest

    def _cli_absent_result(self, manifest_path: Path, to_create: list[dict]) -> PhaseResult:
        self.ctx.trace("  notebooklm CLI not on PATH — manifest emitted, manual create needed")
        for nb in to_create:
            self.ctx.trace(f"    pending: notebooklm create '{nb['name']}'  # {nb['topic']}")
        return PhaseResult(
            status="partial",
            detail=f"CLI absent; {len(to_create)} pending",
            artifacts={"manifest": str(manifest_path), "to_create": [nb["name"] for nb in to_create]},
        )

    def _create_notebooks(self, nb_bin: str, to_create: list[dict]) -> tuple[list[str], list[dict]]:
        created = []
        failed = []
        for nb in to_create:
            self.ctx.trace(f"  notebooklm create '{nb['name']}'")
            r = subprocess.run([nb_bin, "create", nb["name"]], capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                created.append(nb["name"])
            else:
                failed.append({"name": nb["name"], "stderr": r.stderr.strip()[:200]})
                self.ctx.trace(f"    ! failed: {r.stderr.strip()[:120]}")
        return created, failed

    def run(self) -> PhaseResult:
        planned = self._planned_notebooks()
        manifest_path, manifest = self._write_manifest(planned, self._existing_notebooks())
        to_create = [nb for nb in manifest if not nb["already_exists"]]
        nb_bin = shutil.which("notebooklm")
        if not nb_bin:
            return self._cli_absent_result(manifest_path, to_create)
        created, failed = self._create_notebooks(nb_bin, to_create)
        status = "completed" if not failed else "partial"
        return PhaseResult(
            status=status,
            detail=f"{len(created)} created, {len(failed)} failed, {len(planned)-len(to_create)} pre-existing",
            artifacts={"manifest": str(manifest_path), "created": created, "failed": failed},
        )

    def verify(self) -> tuple[bool, str]:
        manifest_path = self.ctx.state_path.parent / "obsidian-restructure-notebooklm-manifest.json"
        if not manifest_path.exists():
            return False, "notebooklm manifest missing"
        return True, "manifest emitted"

    def rollback(self) -> None:
        return
