#!/usr/bin/env python3
"""Collect AST-based quality-debt metrics used by quality rescores."""
from __future__ import annotations

import ast
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence, TextIO

DEFAULT_ROOTS = (Path("scripts"), Path("hooks"), Path("vault"))
FUNCTION_LIMIT = 40
SUBPROCESS_TIMEOUT_FUNCS = {"run", "check_output", "check_call"}


@dataclass(frozen=True)
class FunctionHit:
    """Represent FunctionHit data for this module."""
    path: str
    line: int
    name: str
    lines: int


@dataclass(frozen=True)
class LineHit:
    """Represent LineHit data for this module."""
    path: str
    line: int


@dataclass(frozen=True)
class QualityMetrics:
    """Represent QualityMetrics data for this module."""
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
    public_api_total: int
    public_api_with_docstring: int
    public_api_docstring_coverage_pct: float
    public_api_missing_docstring_hits: list[FunctionHit]


@dataclass
class _FileMetrics:
    long_functions: list[FunctionHit] = field(default_factory=list)
    broad_exceptions: list[LineHit] = field(default_factory=list)
    print_calls: list[LineHit] = field(default_factory=list)
    subprocess_without_timeout: list[LineHit] = field(default_factory=list)
    shell_true_calls: list[LineHit] = field(default_factory=list)
    public_missing: list[FunctionHit] = field(default_factory=list)
    event_calls: int = 0
    public_total: int = 0
    public_documented: int = 0


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


def _public_api_docstring_metrics(tree: ast.Module, path: Path) -> tuple[int, int, list[FunctionHit]]:
    total = 0
    documented = 0
    missing: list[FunctionHit] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or node.name.startswith("_"):
            continue
        total += 1
        if ast.get_docstring(node):
            documented += 1
            continue
        missing.append(FunctionHit(str(path), node.lineno, node.name, _function_lines(node) or 0))
    return total, documented, missing


def _scan_call(node: ast.Call, path: Path, metrics: _FileMetrics) -> None:
    if isinstance(node.func, ast.Name) and node.func.id == "print":
        metrics.print_calls.append(LineHit(str(path), node.lineno))
    if isinstance(node.func, ast.Name) and node.func.id == "event":
        metrics.event_calls += 1
    if _subprocess_call(node) and not _has_timeout(node):
        metrics.subprocess_without_timeout.append(LineHit(str(path), node.lineno))
    if _is_shell_true(node):
        metrics.shell_true_calls.append(LineHit(str(path), node.lineno))


def _scan_nodes(tree: ast.Module, path: Path, metrics: _FileMetrics) -> None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines = _function_lines(node)
            if lines is not None and lines > FUNCTION_LIMIT:
                metrics.long_functions.append(FunctionHit(str(path), node.lineno, node.name, lines))
        elif isinstance(node, ast.ExceptHandler) and _is_broad_handler(node):
            metrics.broad_exceptions.append(LineHit(str(path), node.lineno))
        elif isinstance(node, ast.Call):
            _scan_call(node, path, metrics)


def _scan_file(path: Path) -> _FileMetrics:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    metrics = _FileMetrics()
    metrics.public_total, metrics.public_documented, metrics.public_missing = _public_api_docstring_metrics(tree, path)
    _scan_nodes(tree, path, metrics)
    return metrics


def _merge_metrics(acc: _FileMetrics, item: _FileMetrics) -> None:
    acc.long_functions.extend(item.long_functions)
    acc.broad_exceptions.extend(item.broad_exceptions)
    acc.print_calls.extend(item.print_calls)
    acc.subprocess_without_timeout.extend(item.subprocess_without_timeout)
    acc.shell_true_calls.extend(item.shell_true_calls)
    acc.public_missing.extend(item.public_missing)
    acc.event_calls += item.event_calls
    acc.public_total += item.public_total
    acc.public_documented += item.public_documented


def _sort_metrics(metrics: _FileMetrics) -> None:
    metrics.long_functions.sort(key=lambda hit: (-hit.lines, hit.path, hit.line))
    metrics.broad_exceptions.sort(key=lambda hit: (hit.path, hit.line))
    metrics.print_calls.sort(key=lambda hit: (hit.path, hit.line))
    metrics.subprocess_without_timeout.sort(key=lambda hit: (hit.path, hit.line))
    metrics.shell_true_calls.sort(key=lambda hit: (hit.path, hit.line))
    metrics.public_missing.sort(key=lambda hit: (hit.path, hit.line))


def _public_doc_pct(metrics: _FileMetrics) -> float:
    if metrics.public_total == 0:
        return 100.0
    return round((metrics.public_documented / metrics.public_total) * 100, 2)


def _to_quality_metrics(metrics: _FileMetrics) -> QualityMetrics:
    return QualityMetrics(
        long_functions_gt40=len(metrics.long_functions),
        broad_exceptions=len(metrics.broad_exceptions),
        print_calls=len(metrics.print_calls),
        subprocess_without_timeout=len(metrics.subprocess_without_timeout),
        shell_true_calls=len(metrics.shell_true_calls),
        event_calls=metrics.event_calls,
        long_function_hits=metrics.long_functions,
        broad_exception_hits=metrics.broad_exceptions,
        print_call_hits=metrics.print_calls,
        subprocess_without_timeout_hits=metrics.subprocess_without_timeout,
        shell_true_hits=metrics.shell_true_calls,
        public_api_total=metrics.public_total,
        public_api_with_docstring=metrics.public_documented,
        public_api_docstring_coverage_pct=_public_doc_pct(metrics),
        public_api_missing_docstring_hits=metrics.public_missing,
    )


def collect_metrics(roots: Sequence[Path]) -> QualityMetrics:
    """Provide the public collect metrics API."""
    acc = _FileMetrics()
    for path in _iter_python_files(roots):
        _merge_metrics(acc, _scan_file(path))
    _sort_metrics(acc)
    return _to_quality_metrics(acc)


def main(argv: list[str]) -> int:
    """Run the metric-snapshot command-line entry point."""
    roots = [Path(arg) for arg in argv[1:]] or list(DEFAULT_ROOTS)
    metrics = collect_metrics(roots)
    _write_line(sys.stdout, json.dumps(asdict(metrics), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
