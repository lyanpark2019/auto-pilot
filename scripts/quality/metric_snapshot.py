#!/usr/bin/env python3
"""Collect AST-based quality-debt metrics used by quality rescores."""
from __future__ import annotations

import ast
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence, TextIO

DEFAULT_ROOTS = (Path("scripts"), Path("hooks"), Path("vault"))
FUNCTION_LIMIT = 40


@dataclass(frozen=True)
class FunctionHit:
    path: str
    line: int
    name: str
    lines: int


@dataclass(frozen=True)
class LineHit:
    path: str
    line: int


@dataclass(frozen=True)
class QualityMetrics:
    long_functions_gt40: int
    broad_exceptions: int
    print_calls: int
    long_function_hits: list[FunctionHit]
    broad_exception_hits: list[LineHit]
    print_call_hits: list[LineHit]


def _write_line(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")


def _iter_python_files(roots: Sequence[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or "tests" in path.parts:
                continue
            files.append(path)
    return sorted(files)


def _is_broad_handler(node: ast.ExceptHandler) -> bool:
    if node.type is None:
        return True
    return isinstance(node.type, ast.Name) and node.type.id == "Exception"


def _function_lines(node: ast.AST) -> int | None:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    return end - start + 1


def _scan_file(path: Path) -> tuple[list[FunctionHit], list[LineHit], list[LineHit]]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    long_functions: list[FunctionHit] = []
    broad_exceptions: list[LineHit] = []
    print_calls: list[LineHit] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines = _function_lines(node)
            if lines is not None and lines > FUNCTION_LIMIT:
                long_functions.append(FunctionHit(str(path), node.lineno, node.name, lines))
        elif isinstance(node, ast.ExceptHandler) and _is_broad_handler(node):
            broad_exceptions.append(LineHit(str(path), node.lineno))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            print_calls.append(LineHit(str(path), node.lineno))

    return long_functions, broad_exceptions, print_calls


def collect_metrics(roots: Sequence[Path]) -> QualityMetrics:
    long_functions: list[FunctionHit] = []
    broad_exceptions: list[LineHit] = []
    print_calls: list[LineHit] = []

    for path in _iter_python_files(roots):
        file_long, file_broad, file_prints = _scan_file(path)
        long_functions.extend(file_long)
        broad_exceptions.extend(file_broad)
        print_calls.extend(file_prints)

    long_functions.sort(key=lambda hit: (-hit.lines, hit.path, hit.line))
    broad_exceptions.sort(key=lambda hit: (hit.path, hit.line))
    print_calls.sort(key=lambda hit: (hit.path, hit.line))
    return QualityMetrics(
        long_functions_gt40=len(long_functions),
        broad_exceptions=len(broad_exceptions),
        print_calls=len(print_calls),
        long_function_hits=long_functions,
        broad_exception_hits=broad_exceptions,
        print_call_hits=print_calls,
    )


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv[1:]] or list(DEFAULT_ROOTS)
    metrics = collect_metrics(roots)
    _write_line(sys.stdout, json.dumps(asdict(metrics), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
