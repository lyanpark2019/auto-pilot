#!/usr/bin/env python3
"""Tests for codex-conductor-guard.py hook.

Subprocess-based (mimics harness handing JSON via stdin), so the exit
behavior and stdout payload are exercised end-to-end.

Covers:
  - No marker present -> ALLOW
  - Marker + .py source -> DENY
  - Marker + .md docs -> ALLOW
  - Marker + the marker file itself -> ALLOW
  - Marker + repo `plans/` artifact -> ALLOW
  - Marker AS ANCESTOR named `plans` (e.g. ~/plans/repo/src/main.py) -> DENY
    (regression test for the bypass-leak bug fixed alongside this file)
  - Marker + non-code, non-doc (e.g. .json config) -> ALLOW
  - Non-targeted tool (Bash) -> ALLOW
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
from collections.abc import Callable

HOOK = str(pathlib.Path(__file__).parent / "codex-conductor-guard.py")


def _verdict(fpath: str, tool: str = "Edit") -> str:
    payload = {"tool_name": tool, "tool_input": {"file_path": fpath}}
    r = subprocess.run(
        ["python3", HOOK],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return "DENY" if "deny" in r.stdout else "ALLOW"


def _setup_repo(tmp: str, sub: str = "repo", with_marker: bool = True) -> pathlib.Path:
    repo = pathlib.Path(tmp, sub)
    repo.mkdir(parents=True)
    if with_marker:
        (repo / ".codex-conductor").touch()
    return repo


CaseFn = Callable[[str], tuple[str, str]]
CASES: list[tuple[str, CaseFn]] = []


def case(label: str) -> Callable[[CaseFn], CaseFn]:
    def deco(fn: CaseFn) -> CaseFn:
        CASES.append((label, fn))
        return fn
    return deco


@case("A no marker -> ALLOW")
def _a(tmp: str) -> tuple[str, str]:
    repo = _setup_repo(tmp, with_marker=False)
    f = repo / "main.py"
    f.touch()
    return _verdict(str(f)), "ALLOW"


@case("B marker + .py -> DENY")
def _b(tmp: str) -> tuple[str, str]:
    repo = _setup_repo(tmp)
    f = repo / "main.py"
    f.touch()
    return _verdict(str(f)), "DENY"


@case("C marker + .md -> ALLOW")
def _c(tmp: str) -> tuple[str, str]:
    repo = _setup_repo(tmp)
    f = repo / "README.md"
    f.touch()
    return _verdict(str(f)), "ALLOW"


@case("D marker + marker file itself -> ALLOW")
def _d(tmp: str) -> tuple[str, str]:
    repo = _setup_repo(tmp)
    return _verdict(str(repo / ".codex-conductor")), "ALLOW"


@case("E marker + repo plans/main.py -> ALLOW")
def _e(tmp: str) -> tuple[str, str]:
    repo = _setup_repo(tmp)
    (repo / "plans").mkdir()
    f = repo / "plans" / "main.py"
    f.touch()
    return _verdict(str(f)), "ALLOW"


@case("F ancestor named 'plans' must NOT bypass -> DENY")
def _f(tmp: str) -> tuple[str, str]:
    # Marker INSIDE a path that contains a `plans` ancestor segment.
    # Old buggy logic bypassed via "plans" in parts; correct logic
    # only bypasses when `plans/` is a direct subdir of the marker root.
    nested = pathlib.Path(tmp, "plans", "repo")
    (nested / "src").mkdir(parents=True)
    (nested / ".codex-conductor").touch()
    f = nested / "src" / "main.py"
    f.touch()
    return _verdict(str(f)), "DENY"


@case("G marker + .json config (non-code, non-doc) -> ALLOW")
def _g(tmp: str) -> tuple[str, str]:
    repo = _setup_repo(tmp)
    f = repo / "config.json"
    f.touch()
    return _verdict(str(f)), "ALLOW"


@case("H Bash tool (non-targeted) -> ALLOW")
def _h(tmp: str) -> tuple[str, str]:
    repo = _setup_repo(tmp)
    f = repo / "main.py"
    f.touch()
    return _verdict(str(f), tool="Bash"), "ALLOW"


def main() -> int:
    passed = 0
    for label, fn in CASES:
        with tempfile.TemporaryDirectory() as tmp:
            got, want = fn(tmp)
        ok = got == want
        status = "OK  " if ok else "FAIL"
        print(f"[{status}] {label:55s}  want={want:5s}  got={got:5s}")
        passed += int(ok)
    total = len(CASES)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
