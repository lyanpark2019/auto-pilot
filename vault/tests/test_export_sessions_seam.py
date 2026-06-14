"""Vault export seam: sessions/ pages survive export_obsidian without clobber.

Anti-fabrication: the real hook (hooks/session-distill-stop.sh) is used as the
producer for the sessions page.  The test asserts on the page IT writes, not on
a hand-crafted fixture.

Key assertions
--------------
a) sessions/session-*.md still exists after export_obsidian (not clobbered —
   sessions/ lives outside docs/ so _copy_docs never targets it).
b) The regenerated index.md lists the sessions page.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from pipeline import export  # noqa: E402

HOOK = str(PLUGIN_ROOT.parent / "hooks" / "session-distill-stop.sh")


def _mk_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "my-project"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "overview.md").write_text(
        "---\ntitle: Overview\n---\n\n# Overview\n\nIntroduction.\n"
    )
    # Seed an auto-pilot run so the hook activates.
    planning = repo / ".planning" / "auto-pilot"
    planning.mkdir(parents=True)
    (planning / "state.json").write_text(json.dumps({"run_id": "rSEAM01"}))
    return repo


def _run_hook(repo: Path, vault_path: Path, session_id: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    env["NBM_VAULT_PATH"] = str(vault_path)
    env.pop("VAULT_BUILDER_VAULT", None)
    env.pop("VB_OBSIDIAN_ROOT", None)
    payload = json.dumps({"session_id": session_id})
    return subprocess.run(
        ["bash", HOOK], input=payload, capture_output=True, text=True, env=env
    )


def test_sessions_page_survives_export(tmp_path: Path) -> None:
    """sessions/session-*.md written by the hook is not clobbered by export."""
    repo = _mk_minimal_repo(tmp_path)
    vault_root = tmp_path / "vaults"

    # The vault is <vault_root>/<project_name>; we point NBM_VAULT_PATH there.
    project_name = repo.name
    vault = vault_root / project_name

    # Step 1: hook writes the sessions page into the vault.
    result = _run_hook(repo, vault, session_id="seam-test-01")
    assert result.returncode == 0, f"hook failed: {result.stderr}"

    sessions_dir = vault / "sessions"
    pages_before = list(sessions_dir.glob("session-*.md"))
    assert len(pages_before) == 1, f"expected 1 session page before export, got {pages_before}"
    page_content_before = pages_before[0].read_text(encoding="utf-8")
    assert "rSEAM01" in page_content_before, "run_id not in page"
    assert "seam-test-01" in page_content_before, "session_id not in page"

    # Step 2: run export_obsidian (same vault target).
    export_result = export.export_obsidian(
        repo,
        vault_root=vault_root,
        doc_root=repo / "docs",
        project_name=project_name,
    )
    assert export_result["destination"] == "obsidian"

    # Assertion (a): session page still exists after export (not clobbered).
    pages_after = list(sessions_dir.glob("session-*.md"))
    assert len(pages_after) == 1, (
        f"sessions page clobbered by export_obsidian: {pages_after}"
    )
    assert pages_after[0].read_text(encoding="utf-8") == page_content_before, (
        "sessions page content was modified by export_obsidian"
    )

    # Assertion (b): regenerated index.md mentions the sessions page.
    index_path = vault / "index.md"
    assert index_path.exists(), "index.md not written"
    index_text = index_path.read_text(encoding="utf-8")
    assert "sessions/session-" in index_text, (
        f"sessions page not listed in index.md:\n{index_text}"
    )
