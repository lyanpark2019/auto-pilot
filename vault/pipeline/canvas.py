#!/usr/bin/env python3
"""Emit a JSON-Canvas snapshot of the top god_nodes from `graphify-out/graph.json`.

Writes `<vault>/meta/graph-hub.canvas` containing the top-N nodes by degree
laid out in a grid, plus every edge that connects two top-N nodes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple, TextIO, TypeAlias

JsonObject: TypeAlias = dict[str, object]
CanvasObject: TypeAlias = dict[str, object]


class RankedNode(NamedTuple):
    """Represent RankedNode data for this module."""
    node_id: str
    label: str
    degree: int


def _write_line(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")


def _warn(message: str) -> None:
    _write_line(sys.stderr, message)


def _info(message: str) -> None:
    _write_line(sys.stdout, message)


def _load_graph(graph_path: Path) -> JsonObject | None:
    try:
        raw: object = json.loads(graph_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        _warn(f"canvas: failed to load {graph_path}: {type(exc).__name__}: {exc}")
        return None
    if not isinstance(raw, dict):
        return None
    return {str(key): value for key, value in raw.items()}


def _objects(items: list[object]) -> list[JsonObject]:
    return [
        {str(key): value for key, value in item.items()}
        for item in items
        if isinstance(item, dict)
    ]


def _edge_value(edge: JsonObject, key: str) -> str | None:
    value = edge.get(key)
    return value if isinstance(value, str) else None


def _edge_endpoint(edge: JsonObject, primary: str, alias: str) -> str | None:
    value = edge.get(primary)
    if not value:
        value = edge.get(alias)
    return value if isinstance(value, str) else None


def _degree_by_id(edges: list[object]) -> dict[str, int]:
    degree_by_id: dict[str, int] = {}
    for edge in _objects(edges):
        for key in ("source", "target", "from", "to"):
            value = _edge_value(edge, key)
            if value is not None:
                degree_by_id[value] = degree_by_id.get(value, 0) + 1
    return degree_by_id


def _rank_nodes(nodes: list[object], edges: list[object], max_nodes: int) -> list[RankedNode]:
    degree_by_id = _degree_by_id(edges)
    ranked: list[RankedNode] = []
    for node in _objects(nodes):
        node_id = str(node.get("id") or node.get("label") or "").strip()
        label = str(node.get("label") or node.get("id") or "").strip()
        if node_id and label:
            ranked.append(RankedNode(node_id, label, degree_by_id.get(node_id, 0)))
    ranked.sort(key=lambda node: node.degree, reverse=True)
    return ranked[:max_nodes]


def _canvas_nodes(top: list[RankedNode], id_to_canvas: dict[str, str]) -> list[CanvasObject]:
    cols = 8
    cell_w, cell_h = 280, 140
    canvas_nodes: list[CanvasObject] = []
    for index, node in enumerate(top):
        col, row = index % cols, index // cols
        canvas_nodes.append({
            "id": id_to_canvas[node.node_id],
            "type": "text",
            "text": f"**{node.label}**\n\nDegree: {node.degree}",
            "x": col * cell_w,
            "y": row * cell_h,
            "width": cell_w - 20,
            "height": cell_h - 20,
        })
    return canvas_nodes


def _canvas_edges(edges: list[object], id_to_canvas: dict[str, str]) -> list[CanvasObject]:
    canvas_edges: list[CanvasObject] = []
    seen: set[tuple[str, str]] = set()
    for edge in _objects(edges):
        src = _edge_endpoint(edge, "source", "from")
        tgt = _edge_endpoint(edge, "target", "to")
        if src is None or tgt is None:
            continue
        if src not in id_to_canvas or tgt not in id_to_canvas:
            continue
        edge_key = (id_to_canvas[src], id_to_canvas[tgt])
        if edge_key in seen:
            continue
        seen.add(edge_key)
        canvas_edges.append({
            "id": f"e{len(canvas_edges)}",
            "fromNode": edge_key[0],
            "fromSide": "right",
            "toNode": edge_key[1],
            "toSide": "left",
        })
    return canvas_edges


def emit_graph_canvas(vault: Path, max_nodes: int = 80) -> Path | None:
    """Provide the public emit graph canvas API."""
    vault = vault.expanduser().resolve()
    graph_path = vault / "graphify-out" / "graph.json"
    if not graph_path.exists():
        return None
    graph = _load_graph(graph_path)
    if graph is None:
        return None

    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or graph.get("links") or []
    if not isinstance(nodes, list):
        return None
    edge_list = edges if isinstance(edges, list) else []

    top = _rank_nodes(nodes, edge_list, max_nodes)
    id_to_canvas = {node.node_id: f"n{index}" for index, node in enumerate(top)}
    canvas_path = vault / "meta" / "graph-hub.canvas"
    canvas_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = {
        "nodes": _canvas_nodes(top, id_to_canvas),
        "edges": _canvas_edges(edge_list, id_to_canvas),
    }
    canvas_path.write_text(json.dumps(canvas, indent=2), encoding="utf-8")
    return canvas_path


def main(argv: list[str]) -> int:
    """Run the canvas command-line entry point."""
    parser = argparse.ArgumentParser(prog="canvas")
    parser.add_argument("vault", type=Path)
    parser.add_argument("--max-nodes", type=int, default=80)
    args = parser.parse_args(argv[1:])
    out = emit_graph_canvas(args.vault, max_nodes=args.max_nodes)
    if out is None:
        _warn("[canvas] graph.json missing or invalid; nothing written")
        return 1
    _info(f"[canvas] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
