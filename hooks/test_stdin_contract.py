#!/usr/bin/env python3
"""Self-tests for hooks/_stdin_contract.py.

Script-style (not pytest): exit 0 on all pass, non-zero on any failure.
Run as: python3 hooks/test_stdin_contract.py
"""
from __future__ import annotations

import io
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _stdin_contract import (
    StdinContractError,
    full_payload,
    full_payload_or_none,
    read_tool_input,
    read_tool_input_or_none,
)

CaseFn = Callable[[], tuple[bool, str]]
CASES: list[tuple[str, CaseFn]] = []


def case(label: str) -> Callable[[CaseFn], CaseFn]:
    def deco(fn: CaseFn) -> CaseFn:
        CASES.append((label, fn))
        return fn
    return deco


@case("A valid stdin -> tool_input dict returned")
def _a() -> tuple[bool, str]:
    stream = io.StringIO('{"tool_name":"Bash","tool_input":{"command":"git status"}}')
    result = read_tool_input(stream)
    ok = result == {"command": "git status"}
    return ok, f"got {result!r}"


@case("B not-JSON stdin -> StdinContractError raised")
def _b() -> tuple[bool, str]:
    try:
        read_tool_input(io.StringIO("not valid json {{{{"))
        return False, "no exception raised"
    except StdinContractError as e:
        return True, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"unexpected exception type: {type(e).__name__}: {e}"


@case("C missing tool_input key -> StdinContractError raised")
def _c() -> tuple[bool, str]:
    try:
        read_tool_input(io.StringIO('{"tool_name":"Bash"}'))
        return False, "no exception raised"
    except StdinContractError as e:
        return True, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"unexpected exception type: {type(e).__name__}: {e}"


@case("D non-mapping JSON (list) -> StdinContractError raised")
def _d() -> tuple[bool, str]:
    try:
        read_tool_input(io.StringIO("[1, 2, 3]"))
        return False, "no exception raised"
    except StdinContractError as e:
        return True, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"unexpected exception type: {type(e).__name__}: {e}"


@case("E fail-open helper returns None on bad JSON")
def _e() -> tuple[bool, str]:
    result = read_tool_input_or_none(io.StringIO("bad json !!!"))
    ok = result is None
    return ok, f"got {result!r}"


@case("F fail-open helper returns None on missing tool_input")
def _f() -> tuple[bool, str]:
    result = read_tool_input_or_none(io.StringIO('{"tool_name":"Edit"}'))
    ok = result is None
    return ok, f"got {result!r}"


@case("G fail-open helper returns tool_input dict on valid input")
def _g() -> tuple[bool, str]:
    stream = io.StringIO('{"tool_input":{"file_path":"/tmp/x"}}')
    result = read_tool_input_or_none(stream)
    ok = result == {"file_path": "/tmp/x"}
    return ok, f"got {result!r}"


@case("H full_payload returns entire payload including tool_name")
def _h() -> tuple[bool, str]:
    stream = io.StringIO('{"tool_name":"Edit","tool_input":{"file_path":"/tmp/x"}}')
    result = full_payload(stream)
    ok = result.get("tool_name") == "Edit" and result.get("tool_input") == {"file_path": "/tmp/x"}
    return ok, f"got {result!r}"


@case("I full_payload_or_none returns None on bad JSON")
def _i() -> tuple[bool, str]:
    result = full_payload_or_none(io.StringIO("{broken"))
    ok = result is None
    return ok, f"got {result!r}"


@case("J empty stdin treated as empty object -> missing tool_input -> StdinContractError")
def _j() -> tuple[bool, str]:
    try:
        read_tool_input(io.StringIO(""))
        return False, "no exception raised"
    except StdinContractError as e:
        return True, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"unexpected exception type: {type(e).__name__}: {e}"


@case("K tool_input must be a mapping, not a string -> StdinContractError")
def _k() -> tuple[bool, str]:
    try:
        read_tool_input(io.StringIO('{"tool_input":"not-a-dict"}'))
        return False, "no exception raised"
    except StdinContractError as e:
        return True, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"unexpected exception type: {type(e).__name__}: {e}"


def main() -> int:
    passed = 0
    for label, fn in CASES:
        ok, detail = fn()
        icon = "OK  " if ok else "FAIL"
        print(f"[{icon}] {label}")
        if not ok:
            print(f"       detail: {detail}")
        passed += int(ok)
    total = len(CASES)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
