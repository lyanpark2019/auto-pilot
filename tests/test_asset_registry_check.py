from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import asset_registry_check as arc


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_tokenize_removes_stop_words() -> None:
    assert arc._tokenize("The Auto Pilot Hook") == frozenset({"auto", "pilot", "hook"})


def test_parse_frontmatter_extracts_name_description() -> None:
    data = arc._parse_frontmatter('---\nname: "vault-build"\ndescription: Build vault docs\n---\nbody')
    assert data == {"name": "vault-build", "description": "Build vault docs"}


def test_scan_registry_excludes_hook_tests(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path / "agents" / "reviewer.md", "---\nname: reviewer\ndescription: Review code\n---\n")
    _write(tmp_path / "skills" / "quality" / "SKILL.md", "---\nname: quality\ndescription: Score code\n---\n")
    _write(tmp_path / "hooks" / "guard.py", "# Guard destructive commands\n")
    _write(tmp_path / "hooks" / "test_guard.py", "# test only\n")
    _write(tmp_path / "commands" / "vault.md", "---\ndescription: Build vault\n---\n")
    _write(tmp_path / "codex" / "skills" / "audit" / "SKILL.md", "---\nname: audit\ndescription: Audit code\n---\n")
    monkeypatch.setattr(arc, "REPO_ROOT", tmp_path)

    registry = arc._scan_registry()

    assert {asset.asset_type for asset in registry} == {"agent", "skill", "hook", "command", "codex"}
    assert not any(asset.source.endswith("test_guard.py") for asset in registry)


def test_overlap_detects_name_and_description_similarity() -> None:
    registry = [arc.Asset("vault builder", "build graph docs", "skills/vault/SKILL.md", "skill")]

    by_name = arc._check_overlap("vault export", "unrelated", registry)
    by_desc = arc._check_overlap("other", "build graph docs", registry)

    assert by_name[0]["source"] == "skills/vault/SKILL.md"
    assert "description Jaccard" in by_desc[0]["reason"]


def test_main_writes_overlap_artifact(tmp_path: Path, monkeypatch, capsys) -> None:
    _write(tmp_path / "skills" / "vault" / "SKILL.md", "---\nname: vault build\ndescription: Build docs\n---\n")
    artifact = tmp_path / "artifact.json"
    monkeypatch.setattr(arc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(arc, "_get_head_sha", lambda: "abc123")
    monkeypatch.setattr(
        sys,
        "argv",
        ["asset_registry_check", "--fail-on-overlap", "--name", "vault", "--emit-artifact", str(artifact)],
    )

    assert arc.main() == 1
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["head_sha"] == "abc123"
    assert payload["result"] == "overlap"
    assert payload["overlaps"]
    assert "OVERLAP" in capsys.readouterr().err


def test_main_clean_without_candidate(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(arc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["asset_registry_check"])

    assert arc.main() == 0
    assert "Registry: 0 assets scanned" in capsys.readouterr().err
