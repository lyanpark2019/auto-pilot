from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.graphify_vault_loop import (
    QuerySpec,
    _read_json,
    compact_graphify_vault,
    load_query_manifest,
    run_query_suite,
    default_runner,
    validate_graphify_vault,
)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "auto-pilot"
    graphify = vault / "graphify"
    graphify.mkdir(parents=True)
    (vault / ".obsidian").mkdir()
    _write_json(vault / ".obsidian" / "app.json", {})
    (vault / "index.md").write_text("[[graphify/index]]\n", encoding="utf-8")
    (graphify / "index.md").write_text(
        "[[graphify/_SYSTEM_MAP]]\n[[graphify/graph.canvas]]\n",
        encoding="utf-8",
    )
    (graphify / "_SYSTEM_MAP.md").write_text("[[graphify/_COMMUNITY_Core C000]]\n", encoding="utf-8")
    (graphify / "_COMMUNITY_Core C000.md").write_text(
        "# Core\n\n[[symbol]] [[_private_symbol]]\n",
        encoding="utf-8",
    )
    (graphify / "symbol.md").write_text("# symbol\n", encoding="utf-8")
    (graphify / "symbol_1.md").write_text("# symbol 1\n", encoding="utf-8")
    (graphify / "_private_symbol.md").write_text("# private symbol\n", encoding="utf-8")
    _write_json(
        graphify / "_graph.json",
        {
            "nodes": [
                {"id": "a", "label": "A", "community": 0},
                {"id": "b", "label": "B", "community": 0},
            ],
            "links": [{"source": "a", "target": "b"}],
        },
    )
    _write_json(
        graphify / "graph.canvas",
        {
            "nodes": [
                {"id": "n1", "type": "file", "file": "symbol.md"},
                {"id": "n2", "type": "file", "file": "symbol_1.md"},
                {"id": "n3", "type": "file", "file": "_private_symbol.md"},
            ],
            "edges": [],
        },
    )
    _write_json(graphify / "query-tests" / "summary.json", {"passed": 1, "total": 1})
    (graphify / "query-tests" / "ok.md").write_text("# ok\n", encoding="utf-8")
    return vault


def test_validate_graphify_vault_accepts_required_structure(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)

    result = validate_graphify_vault(vault)

    assert result.ok
    assert result.metrics["communities"] == 1
    assert result.metrics["community_files"] == 1
    assert result.metrics["query_passed"] == 1


def test_compact_graphify_vault_removes_symbol_notes_and_rewrites_canvas(tmp_path: Path) -> None:
    vault = _make_vault(tmp_path)

    result = compact_graphify_vault(vault)

    assert result.removed_files == 3
    assert not (vault / "graphify" / "symbol.md").exists()
    assert not (vault / "graphify" / "symbol_1.md").exists()
    assert not (vault / "graphify" / "_private_symbol.md").exists()
    canvas = json.loads((vault / "graphify" / "graph.canvas").read_text(encoding="utf-8"))
    assert canvas["nodes"] == [
        {"id": "community-0", "type": "file", "file": "_COMMUNITY_Core C000.md", "x": 0, "y": 0, "width": 360, "height": 120}
    ]
    community = (vault / "graphify" / "_COMMUNITY_Core C000.md").read_text(encoding="utf-8")
    assert "[[symbol]]" not in community
    assert "[[_private_symbol]]" not in community
    assert "symbol" in community
    assert "_private_symbol" in community
    assert validate_graphify_vault(vault).ok


def test_run_query_suite_uses_manifest_and_expected_gaps() -> None:
    specs = [
        QuerySpec(name="ok", cmd=["graphify", "explain", "A"], must_contain=["Node: A"]),
        QuerySpec(
            name="gap",
            cmd=["graphify", "explain", "prose-only"],
            must_contain=["No node matching"],
            kind="expected-gap",
        ),
    ]

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        if cmd[-1] == "A":
            return 0, "Node: A\n", ""
        return 0, "No node matching 'prose-only' found.\n", ""

    result = run_query_suite(specs, runner=runner)

    assert result.passed == 2
    assert result.total == 2
    assert not result.failed


def test_default_runner_sets_timeout() -> None:
    completed = subprocess.CompletedProcess(["graphify"], 0, "ok", "")
    with patch("scripts.graphify_vault_loop.subprocess.run", return_value=completed) as run:
        assert default_runner(["graphify", "explain", "A"]) == (0, "ok", "")
    assert run.call_args.kwargs["timeout"] == 120


def test_default_runner_reports_timeout() -> None:
    exc = subprocess.TimeoutExpired(["graphify"], timeout=120, output="partial", stderr="slow")
    with patch("scripts.graphify_vault_loop.subprocess.run", side_effect=exc):
        rc, stdout, stderr = default_runner(["graphify", "query", "slow"])
    assert rc == 124
    assert stdout == "partial"
    assert "timeout after 120s" in stderr


def test_load_query_manifest_accepts_wrapped_tests(tmp_path: Path) -> None:
    manifest = tmp_path / "queries.json"
    manifest.write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "name": "explain-core",
                        "cmd": ["graphify", "explain", "Core"],
                        "must_contain": ["Node: Core"],
                        "kind": "expected-gap",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    specs = load_query_manifest(manifest)

    assert specs == [
        QuerySpec(
            name="explain-core",
            cmd=["graphify", "explain", "Core"],
            must_contain=["Node: Core"],
            kind="expected-gap",
        )
    ]


def test_run_query_suite_writes_artifacts_and_summary(tmp_path: Path) -> None:
    specs = [
        QuerySpec(name="ok", cmd=["graphify", "explain", "A"], must_contain=["Node: A"]),
        QuerySpec(name="bad", cmd=["graphify", "explain", "B"], must_contain=["Node: B"]),
    ]

    def runner(cmd: list[str]) -> tuple[int, str, str]:
        if cmd[-1] == "A":
            return 0, "Node: A\n", ""
        return 1, "missing\n", "boom\n"

    result = run_query_suite(specs, runner=runner, out_dir=tmp_path)

    assert result.passed == 1
    assert [failure.name for failure in result.failed] == ["bad"]
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] == 1
    assert summary["failed"][0]["name"] == "bad"
    assert "STDERR" in (tmp_path / "bad.txt").read_text(encoding="utf-8")
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "FAIL" in readme
    assert "[[graphify/query-tests/bad|bad]]" in readme


def test_read_json_records_parse_errors(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")
    issues: list[str] = []

    assert _read_json(path, issues) == {}

    assert issues
    assert "JSONDecodeError" in issues[0]


def test_read_json_does_not_swallow_unexpected_runtime_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{}", encoding="utf-8")

    def boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("scripts.graphify_vault_loop.json.loads", boom)

    with pytest.raises(RuntimeError, match="boom"):
        _read_json(path, [])
