"""Tests for graphify JSON to Obsidian JSON Canvas export."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from pipeline.canvas import emit_graph_canvas  # noqa: E402


def _write_graph(vault: Path, graph: dict[str, object]) -> None:
    graph_path = vault / "graphify-out" / "graph.json"
    graph_path.parent.mkdir(parents=True)
    graph_path.write_text(json.dumps(graph), encoding="utf-8")


def test_emit_graph_canvas_writes_ranked_nodes_and_deduped_edges(tmp_path: Path) -> None:
    _write_graph(
        tmp_path,
        {
            "nodes": [
                {"id": "auth", "label": "Auth"},
                {"id": "billing", "label": "Billing"},
                {"id": "docs", "label": "Docs"},
            ],
            "edges": [
                {"source": "auth", "target": "billing"},
                {"source": "auth", "target": "billing"},
                {"from": "docs", "to": "auth"},
                {"source": "auth", "target": "external"},
            ],
        },
    )

    out = emit_graph_canvas(tmp_path, max_nodes=3)

    assert out == tmp_path / "meta" / "graph-hub.canvas"
    canvas = json.loads(out.read_text(encoding="utf-8"))
    assert [node["text"] for node in canvas["nodes"]] == [
        "**Auth**\n\nDegree: 4",
        "**Billing**\n\nDegree: 2",
        "**Docs**\n\nDegree: 1",
    ]
    assert canvas["edges"] == [
        {
            "id": "e0",
            "fromNode": "n0",
            "fromSide": "right",
            "toNode": "n1",
            "toSide": "left",
        },
        {
            "id": "e1",
            "fromNode": "n2",
            "fromSide": "right",
            "toNode": "n0",
            "toSide": "left",
        },
    ]


def test_emit_graph_canvas_returns_none_for_missing_graph(tmp_path: Path) -> None:
    assert emit_graph_canvas(tmp_path) is None
    assert not (tmp_path / "meta" / "graph-hub.canvas").exists()


def test_emit_graph_canvas_returns_none_for_invalid_graph(tmp_path: Path) -> None:
    graph_path = tmp_path / "graphify-out" / "graph.json"
    graph_path.parent.mkdir(parents=True)
    graph_path.write_text("{not-json", encoding="utf-8")

    assert emit_graph_canvas(tmp_path) is None
    assert not (tmp_path / "meta" / "graph-hub.canvas").exists()
