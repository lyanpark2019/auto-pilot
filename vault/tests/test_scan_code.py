from __future__ import annotations

import ast

import pytest

from pipeline import scan_code


def _function_node() -> ast.FunctionDef:
    node = ast.parse("def f(x):\n    pass\n").body[0]
    assert isinstance(node, ast.FunctionDef)
    return node


def test_sig_handles_expected_unparse_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    node = _function_node()

    def fail_unparse(value: object) -> str:
        raise ValueError("bad ast")

    monkeypatch.setattr(ast, "unparse", fail_unparse)

    assert scan_code._sig(node) == "f(...)"


def test_sig_does_not_swallow_unexpected_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    node = _function_node()

    def fail_unparse(value: object) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(ast, "unparse", fail_unparse)

    with pytest.raises(RuntimeError, match="boom"):
        scan_code._sig(node)
