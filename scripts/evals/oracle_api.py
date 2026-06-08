"""General per-case oracle contract + helpers.

A case ``oracle.py`` exports ``check(workdir, run) -> OracleResult``. This module
loads it and offers a deterministic shell-command verifier. It does NOT wrap
``_dogfood_gate`` (that is the separate harness-health gate, Gate 2).
"""
from __future__ import annotations

import importlib.util
import os
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

from evals._types import OracleResult, RunResult

CheckFn = Callable[[Path, RunResult], OracleResult]

_CASES_DIR = Path(__file__).resolve().parent.parent.parent / "evals" / "cases"


def load_case_oracle(case_id: str) -> CheckFn:
    """Import ``evals/cases/<case_id>/oracle.py`` and return its ``check``."""
    path = _CASES_DIR / case_id / "oracle.py"
    if not path.exists():
        raise ImportError(f"oracle not found: {path}")
    spec = importlib.util.spec_from_file_location(f"evals_case_{case_id}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load oracle at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "check"):
        raise ImportError(f"oracle at {path} has no 'check' function")
    return module.check  # type: ignore[no-any-return]


def run_verify_cmd(workdir: Path, cmd: str, timeout: int = 120) -> tuple[bool, str]:
    """Run a Verify cmd in ``workdir``; return ``(ok, detail)``."""
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            cwd=str(workdir),
            env={"PYTHONPATH": str(workdir), "PATH": _safe_path()},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (False, f"timeout after {timeout}s: {cmd}")
    except ValueError as exc:
        return (False, f"invalid verify command: {type(exc).__name__}: {exc}")
    detail = (proc.stdout + proc.stderr).strip()[-500:]
    return (proc.returncode == 0, detail)


def _safe_path() -> str:
    return os.environ.get("PATH", "/usr/bin:/bin")
