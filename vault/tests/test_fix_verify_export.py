"""Tests for fix plan builder + verify + export."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from pipeline import fix, verify, export  # noqa: E402


def _mk_project(tmp_path: Path) -> Path:
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "auth.py").write_text(
        '"""Auth."""\ndef login(user: str, password: str) -> bool:\n    return True\n'
    )
    (repo / "docs").mkdir()
    (repo / "docs" / "auth.md").write_text(
        "---\nsource_files: [\"src/auth.py\"]\n---\n\n# Auth\n\nCall `login(user)` to auth.\n"
    )
    return repo


def test_fix_plan_groups_by_drift_type(tmp_path: Path) -> None:
    repo = _mk_project(tmp_path)
    # Add a gap module
    (repo / "src" / "billing.py").write_text("def charge() -> int:\n    return 0\n")
    # Add an orphan ref
    (repo / "docs" / "stale.md").write_text("# stale\n\nSee `src/removed.py`.\n")

    plan = fix.build_plan(repo)
    assert plan["drift_summary"]["gap"] >= 1
    assert plan["drift_summary"]["orphan"] >= 1
    assert plan["drift_summary"]["claim_drift"] >= 1
    workers = {t["worker_type"] for t in plan["tickets"]}
    assert "vault-knowledge-author" in workers
    assert "vault-structure-curator" in workers


def test_verify_runs_against_code_docs_rubric(tmp_path: Path) -> None:
    repo = _mk_project(tmp_path)
    result = verify.verify(repo)
    assert "dimensions" in result
    assert "total" in result
    assert isinstance(result["pass"], bool)
    # Should produce per-dim scores
    assert "hallucination" in result["dimensions"]
    assert "completeness" in result["dimensions"]


def test_verify_completeness_zero_when_full_gap(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("def public_fn(): pass\n")
    (repo / "src" / "b.py").write_text("def another_fn(): pass\n")
    # No docs at all → completeness should be low
    (repo / "docs").mkdir()
    result = verify.verify(repo)
    assert result["dimensions"]["completeness"]["score"] < result["dimensions"]["completeness"]["max"]


def test_export_obsidian_upsert_creates_when_missing(tmp_path: Path) -> None:
    repo = _mk_project(tmp_path)
    vault_root = tmp_path / "vaults"
    result = export.export_obsidian(repo, vault_root=vault_root, project_name="proj")
    assert result["created_new"] is True
    assert (vault_root / "proj" / "auth.md").exists()
    assert (vault_root / "proj" / "index.md").exists()


def test_export_obsidian_preserves_manual_edit(tmp_path: Path) -> None:
    repo = _mk_project(tmp_path)
    vault_root = tmp_path / "vaults"
    # First run — fresh
    export.export_obsidian(repo, vault_root=vault_root, project_name="proj")
    # Modify vault page to manual_edit
    (vault_root / "proj" / "auth.md").write_text(
        "---\nsource_files: [\"src/auth.py\"]\nmanual_edit: true\n---\n\n# Custom Auth Doc\n"
    )
    # Change repo doc
    (repo / "docs" / "auth.md").write_text("---\nsource_files: [\"src/auth.py\"]\n---\n# DIFFERENT\n")
    # Re-export — should NOT overwrite manual_edit page
    result = export.export_obsidian(repo, vault_root=vault_root, project_name="proj")
    assert result["created_new"] is False
    assert "Custom Auth Doc" in (vault_root / "proj" / "auth.md").read_text()
    assert result["manual_pages_preserved"] >= 1


def test_export_all_handles_unknown_destination(tmp_path: Path) -> None:
    repo = _mk_project(tmp_path)
    results = export.export_all(repo, ["bogus"])
    assert "error" in results["bogus"]
    assert results["bogus"]["failed"] is True


def test_export_all_does_not_swallow_unexpected_state_parser_errors(tmp_path: Path, monkeypatch) -> None:
    repo = _mk_project(tmp_path)
    state_file = repo / ".vault-builder" / "state.json"
    state_file.parent.mkdir()
    state_file.write_text("{}", encoding="utf-8")

    def broken_loads(raw: str) -> object:
        raise RuntimeError("parser bug")

    monkeypatch.setattr(export.json, "loads", broken_loads)

    with pytest.raises(RuntimeError, match="parser bug"):
        export.export_all(repo, [])


def test_export_script_mode_bases_canvas(tmp_path: Path) -> None:
    """Documented invocation (python3 $ROOT/pipeline/export.py) must work for
    bases/canvas — these use sibling-module imports that broke without the
    __package__ sys.path guard (silent 'attempted relative import' in report)."""
    repo = _mk_project(tmp_path)
    script = PLUGIN_ROOT / "pipeline" / "export.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(repo), "--export", "bases,canvas",
         "--obsidian-path", str(tmp_path / "vaults")],
        capture_output=True, text=True,
    )
    assert "attempted relative import" not in proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    # Fixture has no wikitree/ or graph.json → both skip gracefully, neither fails.
    assert report["exports"]["bases"].get("skipped") is True
    assert report["exports"]["canvas"].get("skipped") is True
    assert proc.returncode == 0


def test_export_script_mode_failure_exits_nonzero(tmp_path: Path) -> None:
    """Per-destination failure must be surfaced: failed flag + non-zero exit
    (previously swallowed into the JSON report with exit 0)."""
    repo = _mk_project(tmp_path)
    script = PLUGIN_ROOT / "pipeline" / "export.py"
    proc = subprocess.run(
        [sys.executable, str(script), str(repo), "--export", "bogus"],
        capture_output=True, text=True,
    )
    report = json.loads(proc.stdout)
    assert report["exports"]["bogus"]["failed"] is True
    assert proc.returncode == 1
    assert "EXPORT FAILED" in proc.stderr


def test_export_graphify_skips_when_binary_missing(tmp_path: Path, monkeypatch) -> None:
    repo = _mk_project(tmp_path)
    monkeypatch.setattr(export, "GRAPHIFY_BIN", "/nonexistent/graphify")
    result = export.export_graphify(repo)
    assert result.get("skipped") is True


def test_auto_graphify_update_forces_existing_graph_refresh(tmp_path: Path, monkeypatch) -> None:
    repo = _mk_project(tmp_path)
    graph = repo / "graphify-out" / "graph.json"
    graph.parent.mkdir()
    graph.write_text("{}")
    commands: list[list[str]] = []

    def fake_run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
        commands.append(cmd)
        return 0, "ok", ""

    monkeypatch.setattr(export, "GRAPHIFY_BIN", "/bin/echo")
    monkeypatch.setattr(export, "_run", fake_run)

    export.auto_graphify_update(repo, merge_global=False)

    assert commands[0] == ["/bin/echo", "update", str(repo.resolve()), "--force"]
