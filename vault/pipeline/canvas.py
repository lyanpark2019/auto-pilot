#!/usr/bin/env python3
"""Emit a JSON-Canvas snapshot of the top god_nodes from `graphify-out/graph.json`.

Writes `<vault>/meta/graph-hub.canvas` containing the top-N nodes (by degree)
laid out in a grid + every edge that connects two top-N nodes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def emit_graph_canvas(vault: Path, max_nodes: int = 80) -> Path | None:
    vault = vault.expanduser().resolve()
    graph_path = vault / "graphify-out" / "graph.json"
    if not graph_path.exists():
        return None
    try:
        graph = json.loads(graph_path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"canvas: failed to load {graph_path}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    if not isinstance(graph, dict):
        return None
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or graph.get("links") or []
    if not isinstance(nodes, list):
        return None

    degree_by_id: dict[str, int] = {}
    for e in edges:
        if not isinstance(e, dict):
            continue
        for key in ("source", "target", "from", "to"):
            val = e.get(key)
            if isinstance(val, str):
                degree_by_id[val] = degree_by_id.get(val, 0) + 1

    ranked: list[tuple[str, str, int]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or node.get("label") or "").strip()
        label = str(node.get("label") or node.get("id") or "").strip()
        if not node_id or not label:
            continue
        ranked.append((node_id, label, degree_by_id.get(node_id, 0)))
    ranked.sort(key=lambda triple: triple[2], reverse=True)
    top = ranked[:max_nodes]
    id_to_canvas = {node_id: f"n{i}" for i, (node_id, _, _) in enumerate(top)}

    cols = 8
    cell_w, cell_h = 280, 140
    canvas_nodes = []
    for i, (node_id, label, deg) in enumerate(top):
        col, row = i % cols, i // cols
        canvas_nodes.append({
            "id": id_to_canvas[node_id],
            "type": "text",
            "text": f"**{label}**\n\nDegree: {deg}",
            "x": col * cell_w,
            "y": row * cell_h,
            "width": cell_w - 20,
            "height": cell_h - 20,
        })
    canvas_edges = []
    seen: set[tuple[str, str]] = set()
    for e in edges:
        if not isinstance(e, dict):
            continue
        src = e.get("source") or e.get("from")
        tgt = e.get("target") or e.get("to")
        if not (isinstance(src, str) and isinstance(tgt, str)):
            continue
        if src not in id_to_canvas or tgt not in id_to_canvas:
            continue
        key = (id_to_canvas[src], id_to_canvas[tgt])
        if key in seen:
            continue
        seen.add(key)
        canvas_edges.append({
            "id": f"e{len(canvas_edges)}",
            "fromNode": key[0],
            "fromSide": "right",
            "toNode": key[1],
            "toSide": "left",
        })

    canvas_path = vault / "meta" / "graph-hub.canvas"
    canvas_path.parent.mkdir(parents=True, exist_ok=True)
    canvas_path.write_text(
        json.dumps({"nodes": canvas_nodes, "edges": canvas_edges}, indent=2),
        encoding="utf-8",
    )
    return canvas_path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="canvas")
    parser.add_argument("vault", type=Path)
    parser.add_argument("--max-nodes", type=int, default=80)
    args = parser.parse_args(argv[1:])
    out = emit_graph_canvas(args.vault, max_nodes=args.max_nodes)
    if out is None:
        print("[canvas] graph.json missing or invalid; nothing written", file=sys.stderr)
        return 1
    print(f"[canvas] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
