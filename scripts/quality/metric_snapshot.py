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
SUBPROCESS_TIMEOUT_FUNCS = {"run", "check_output", "check_call"}


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
    subprocess_without_timeout: int
    shell_true_calls: int
    event_calls: int
    long_function_hits: list[FunctionHit]
    broad_exception_hits: list[LineHit]
    print_call_hits: list[LineHit]
    subprocess_without_timeout_hits: list[LineHit]
    shell_true_hits: list[LineHit]


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
            if "__pycache__" in path.parts or "tests" in path.parts or path.name.startswith("test_"):
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


def _subprocess_call(node: ast.Call) -> str | None:
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name) or func.value.id != "subprocess":
        return None
    return func.attr if func.attr in SUBPROCESS_TIMEOUT_FUNCS else None


def _has_timeout(node: ast.Call) -> bool:
    return any(keyword.arg == "timeout" for keyword in node.keywords)


def _is_shell_true(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
            return keyword.value.value is True
    return False


def _scan_file(path: Path) -> tuple[list[FunctionHit], list[LineHit], list[LineHit], list[LineHit], list[LineHit], int]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    long_functions: list[FunctionHit] = []
    broad_exceptions: list[LineHit] = []
    print_calls: list[LineHit] = []
    subprocess_without_timeout: list[LineHit] = []
    shell_true_calls: list[LineHit] = []
    event_calls = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines = _function_lines(node)
            if lines is not None and lines > FUNCTION_LIMIT:
                long_functions.append(FunctionHit(str(path), node.lineno, node.name, lines))
        elif isinstance(node, ast.ExceptHandler) and _is_broad_handler(node):
            broad_exceptions.append(LineHit(str(path), node.lineno))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                print_calls.append(LineHit(str(path), node.lineno))
            if isinstance(node.func, ast.Name) and node.func.id == "event":
                event_calls += 1
            if _subprocess_call(node) and not _has_timeout(node):
                subprocess_without_timeout.append(LineHit(str(path), node.lineno))
            if _is_shell_true(node):
                shell_true_calls.append(LineHit(str(path), node.lineno))

    return long_functions, broad_exceptions, print_calls, subprocess_without_timeout, shell_true_calls, event_calls


def collect_metrics(roots: Sequence[Path]) -> QualityMetrics:
    long_functions: list[FunctionHit] = []
    broad_exceptions: list[LineHit] = []
    print_calls: list[LineHit] = []
    subprocess_without_timeout: list[LineHit] = []
    shell_true_calls: list[LineHit] = []
    event_calls = 0

    for path in _iter_python_files(roots):
        file_long, file_broad, file_prints, file_timeouts, file_shell_true, file_events = _scan_file(path)
        long_functions.extend(file_long)
        broad_exceptions.extend(file_broad)
        print_calls.extend(file_prints)
        subprocess_without_timeout.extend(file_timeouts)
        shell_true_calls.extend(file_shell_true)
        event_calls += file_events

    long_functions.sort(key=lambda hit: (-hit.lines, hit.path, hit.line))
    broad_exceptions.sort(key=lambda hit: (hit.path, hit.line))
    print_calls.sort(key=lambda hit: (hit.path, hit.line))
    subprocess_without_timeout.sort(key=lambda hit: (hit.path, hit.line))
    shell_true_calls.sort(key=lambda hit: (hit.path, hit.line))
    return QualityMetrics(
        long_functions_gt40=len(long_functions),
        broad_exceptions=len(broad_exceptions),
        print_calls=len(print_calls),
        subprocess_without_timeout=len(subprocess_without_timeout),
        shell_true_calls=len(shell_true_calls),
        event_calls=event_calls,
        long_function_hits=long_functions,
        broad_exception_hits=broad_exceptions,
        print_call_hits=print_calls,
        subprocess_without_timeout_hits=subprocess_without_timeout,
        shell_true_hits=shell_true_calls,
    )


def main(argv: list[str]) -> int:
    roots = [Path(arg) for arg in argv[1:]] or list(DEFAULT_ROOTS)
    metrics = collect_metrics(roots)
    _write_line(sys.stdout, json.dumps(asdict(metrics), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
