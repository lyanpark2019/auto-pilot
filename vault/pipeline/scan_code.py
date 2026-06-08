#!/usr/bin/env python3
"""Extract public symbols from a code tree via AST.

Returns per-module map:
    {
      "relative/path/module.py": {
        "public_classes": ["Foo", "Bar"],
        "public_functions": ["fn_a"],
        "signatures": {"fn_a": "fn_a(x: int, y: str = 'z') -> bool"},
        "docstring_first_line": "...",
        "size_bytes": 1234,
      },
      ...
    }

Currently Python-only. TODO: TS/JS via tree-sitter.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any, TextIO

# Support running both as `python3 -m pipeline.scan_code` and `python3 pipeline/scan_code.py`
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sources._excludes import is_excluded

# Public-API scan skips these ON TOP OF the shared BASE_EXCLUDES: migrations,
# the whole .claude tree, vendored third-party, and tests (behaviour docs,
# not API surface). Worktree/junk dirs live in BASE_EXCLUDES (sources/_excludes).
_API_EXCLUDES = (
    "**/migrations/**", "**/.claude/**",
    "**/.tools/**", "**/site-packages/**", "**/vendor/**", "**/third_party/**",
    "**/tests/**", "**/test_*.py", "**/conftest.py",
)


def _write_line(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")


def _warn(message: str) -> None:
    _write_line(sys.stderr, message)


def _sig(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render function signature as `name(args) -> ret`."""
    try:
        sig_inner = ast.unparse(node.args)
    except (AttributeError, RecursionError, TypeError, ValueError) as exc:
        _warn(f"scan_code: failed to unparse args for {node.name}: error_type={type(exc).__name__}: {exc}")
        sig_inner = "..."
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}{node.name}({sig_inner}){ret}"


def scan_module(path: Path) -> dict[str, Any]:
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError):
        return {"public_classes": [], "public_functions": [], "signatures": {},
                "docstring_first_line": "", "size_bytes": path.stat().st_size, "error": "parse_failed"}

    classes: list[str] = []
    functions: list[str] = []
    signatures: dict[str, str] = {}
    docstring = ast.get_docstring(tree) or ""

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            functions.append(node.name)
            signatures[node.name] = _sig(node)

    return {
        "public_classes": classes,
        "public_functions": functions,
        "signatures": signatures,
        "docstring_first_line": docstring.split("\n", 1)[0].strip(),
        "size_bytes": path.stat().st_size,
    }


def scan_tree(root: Path, extras: list[str] | None = None) -> dict[str, dict[str, Any]]:
    root = root.expanduser().resolve()
    extras = extras or []
    out: dict[str, dict[str, Any]] = {}
    for p in root.rglob("*.py"):
        if not p.is_file():
            continue
        if is_excluded(p, root, [*_API_EXCLUDES, *extras]):
            continue
        rel = str(p.relative_to(root))
        out[rel] = scan_module(p)
    return out


def main(argv: list[str]) -> int:
    import json
    import sys
    if len(argv) < 2:
        sys.stderr.write("usage: scan_code.py <repo>\n")
        return 1
    result = scan_tree(Path(argv[1]))
    sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv))
