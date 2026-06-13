#!/usr/bin/env python3
"""Minimal stdio MCP server exposing vault query tools.

Tools:
- vault_query(question, vault, budget?)  → graphify query result
- vault_path(a, b, vault)               → graphify path between nodes
- vault_explain(concept, vault)         → graphify explain
- vault_audit_status(vault)             → latest score-state + content-state + ticket counts

Protocol: JSON-RPC 2.0 line-delimited over stdio (MCP baseline).
Run via Claude Code's .mcp.json — vault path passed via env NBM_VAULT_PATH or per-call arg.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

GRAPHIFY = os.environ.get("GRAPHIFY_BIN", str(Path.home() / ".local/bin/graphify"))
DEFAULT_VAULT = os.environ.get("NBM_VAULT_PATH", "")


def _warn(message: str) -> None:
    sys.stderr.write(f"{message}\n")


_VAULT_PROP = {"type": "string", "description": "Vault root path (optional, defaults to NBM_VAULT_PATH env)"}
_CAT_PROP = {"type": "string", "description": "Category subdirectory under <vault> (optional; if omitted, all categories are searched in deterministic alphabetical order)"}

TOOLS = [
    {
        "name": "vault_query",
        "description": "Query the vault knowledge graph with a natural-language question.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "vault": _VAULT_PROP,
                "category": _CAT_PROP,
                "budget": {"type": "integer", "default": 500},
            },
            "required": ["question"],
        },
    },
    {
        "name": "vault_path",
        "description": "Find a path between two concepts/entities in the vault graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "string"},
                "vault": _VAULT_PROP,
                "category": _CAT_PROP,
            },
            "required": ["a", "b"],
        },
    },
    {
        "name": "vault_explain",
        "description": "Get a structured explanation of a concept from the vault.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "concept": {"type": "string"},
                "vault": _VAULT_PROP,
                "category": _CAT_PROP,
            },
            "required": ["concept"],
        },
    },
    {
        "name": "vault_audit_status",
        "description": "Return latest structural + content scores and PM ticket counts.",
        "inputSchema": {
            "type": "object",
            "properties": {"vault": _VAULT_PROP},
        },
    },
]


def _vault(args: dict[str, Any]) -> Path:
    v = args.get("vault") or DEFAULT_VAULT
    if not v:
        raise ValueError("vault path required (arg or NBM_VAULT_PATH env)")
    return Path(v).expanduser().resolve()


def _raw_dirs(vault: Path, args: dict[str, Any]) -> list[Path]:
    """Resolve target raw/ directories. Honors optional `category` arg.

    Without category: returns all `<vault>/<cat>/raw` dirs in alphabetical order
    (deterministic — no arbitrary first-match). Single-cat vaults get one entry.
    With category: returns just that one (raises if missing).
    """
    cat = args.get("category")
    if cat:
        target = vault / cat / "raw"
        if not target.is_dir():
            raise ValueError(f"category '{cat}' not found at {target}")
        return [target]
    dirs = sorted(p for p in vault.glob("*/raw") if p.is_dir())
    return dirs or [vault]


def _run_graphify(cwd: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            [GRAPHIFY, *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if out.returncode != 0:
            return f"[graphify error rc={out.returncode}] {out.stderr.strip()}"
        return out.stdout.strip()
    except subprocess.TimeoutExpired:
        return "[graphify timeout]"
    except FileNotFoundError:
        return f"[graphify binary not found: {GRAPHIFY}]"


def _multi_run(dirs: list[Path], *graphify_args: str) -> str:
    if len(dirs) == 1:
        return _run_graphify(dirs[0], *graphify_args)
    parts = []
    for d in dirs:
        parts.append(f"### {d.parent.name}\n{_run_graphify(d, *graphify_args)}")
    return "\n\n".join(parts)


def tool_vault_query(args: dict[str, Any]) -> dict[str, Any]:
    """Handle the vault query MCP tool."""
    vault = _vault(args)
    q = args["question"]
    budget = args.get("budget", 500)
    dirs = _raw_dirs(vault, args)
    return {"content": [{"type": "text", "text": _multi_run(dirs, "query", q, "--budget", str(budget))}]}


def tool_vault_path(args: dict[str, Any]) -> dict[str, Any]:
    """Handle the vault path MCP tool."""
    vault = _vault(args)
    dirs = _raw_dirs(vault, args)
    return {"content": [{"type": "text", "text": _multi_run(dirs, "path", args["a"], args["b"])}]}


def tool_vault_explain(args: dict[str, Any]) -> dict[str, Any]:
    """Handle the vault explain MCP tool."""
    vault = _vault(args)
    dirs = _raw_dirs(vault, args)
    return {"content": [{"type": "text", "text": _multi_run(dirs, "explain", args["concept"])}]}


def tool_vault_audit_status(args: dict[str, Any]) -> dict[str, Any]:
    """Handle the vault audit status MCP tool."""
    vault = _vault(args)
    meta = vault / "meta"
    status: dict[str, Any] = {"vault": str(vault)}
    for name, fname in [("structural", "score-state.json"), ("content", "score-content-state.json")]:
        p = meta / fname
        if p.exists():
            try:
                status[name] = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError) as e:
                _warn(f"mcp_vault_server: failed to parse {fname} error_type={type(e).__name__}: {e}")
                status[name] = {"error": str(e)}
    ts = meta / "ticket-state.json"
    if ts.exists():
        try:
            t = json.loads(ts.read_text())
            tickets = t.get("tickets", [])
            status["tickets"] = {
                "total": len(tickets),
                "verified": sum(1 for x in tickets if x.get("status") == "verified"),
                "rejected": sum(1 for x in tickets if x.get("status") == "rejected"),
                "escalated": sum(1 for x in tickets if x.get("status") == "escalated"),
            }
        except (OSError, json.JSONDecodeError, AttributeError, TypeError) as e:
            _warn(f"mcp_vault_server: failed to parse ticket-state.json error_type={type(e).__name__}: {e}")
            status["tickets"] = {"error": str(e)}
    return {"content": [{"type": "text", "text": json.dumps(status, indent=2, ensure_ascii=False)}]}


DISPATCH = {
    "vault_query": tool_vault_query,
    "vault_path": tool_vault_path,
    "vault_explain": tool_vault_explain,
    "vault_audit_status": tool_vault_audit_status,
}


def _respond(req_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(req: dict[str, Any]) -> None:
    """Provide the public handle API."""
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        client_proto = params.get("protocolVersion") if isinstance(params, dict) else None
        supported = {"2025-06-18", "2025-03-26", "2024-11-05"}
        proto = client_proto if client_proto in supported else "2025-06-18"
        _respond(rid, {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "notebooklm-vault", "version": "0.2.0"},
        })
    elif method == "tools/list":
        _respond(rid, {"tools": TOOLS})
    elif method == "tools/call":
        name = str(params.get("name") or "")
        args = params.get("arguments") or {}
        fn = DISPATCH.get(name)
        if not fn:
            _respond(rid, error={"code": -32601, "message": f"unknown tool: {name}"})
            return
        try:
            _respond(rid, fn(args))
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            _warn(f"mcp_vault_server: tool={name} error_type={type(e).__name__}: {e}")
            _respond(rid, error={"code": -32000, "message": str(e)})
    elif method in ("notifications/initialized", "notifications/cancelled"):
        return  # no response for notifications
    else:
        if rid is not None:
            _respond(rid, error={"code": -32601, "message": f"method not found: {method}"})


def main() -> int:
    """Run the mcp-vault-server command-line entry point."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            _warn(f"mcp_vault_server: skipping malformed JSON line: {type(exc).__name__}: {exc}")
            continue
        handle(req)
    return 0


if __name__ == "__main__":
    sys.exit(main())
