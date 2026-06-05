"""Task-success oracle for the dogfood smoke case.

Asserts the deliverable via the smoke spec's two Verify cmds. Producer-agnostic:
never reads .planning/auto-pilot internals.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running both in-tree (pytest) and as a loaded module file.
# Guarded: this file is re-exec'd on every load_case_oracle() call (it is not
# cached in sys.modules), so an unguarded insert would grow sys.path per run.
_SCRIPTS_ROOT = str(Path(__file__).resolve().parents[3] / "scripts")
if _SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, _SCRIPTS_ROOT)

from evals._types import OracleResult, RunResult  # noqa: E402
from evals.oracle_api import run_verify_cmd  # noqa: E402

# NB: VERIFY_CMDS[1] uses `python3 -m pytest` (not bare `pytest` as the prose
# spec shows) so it resolves under run_verify_cmd's minimal PATH/PYTHONPATH env.
VERIFY_CMDS = (
    'python3 -c "from scripts._dogfood_noop import dogfood_identity; '
    'assert dogfood_identity(7) == 7"',
    "python3 -m pytest -q tests/test_dogfood_noop.py",
)


def check(workdir: Path, run: RunResult) -> OracleResult:
    for cmd in VERIFY_CMDS:
        ok, detail = run_verify_cmd(workdir, cmd)
        if not ok:
            return OracleResult(outcome="fail", reason=f"{cmd} -> {detail or '(no output)'}")
    return OracleResult(outcome="pass", reason="")
