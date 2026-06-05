"""Per-case attempt runner: isolate via a fresh clone, run auto-pilot headless,
then the case oracle. Teardown is in a ``finally`` (round-3 P2-D)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from evals._types import OracleResult, RunResult
from evals.oracle_api import load_case_oracle

_REPO = Path(__file__).resolve().parent.parent.parent
_INIT = "scripts/orchestrator.py"
_LOOP = "scripts/headless-loop.py"


def run_case(
    case_id: str,
    repo: Path = _REPO,
    run_id: str = "local",
    max_iter: int = 20,
    max_cost_usd: float = 5.0,
) -> OracleResult:
    """Run one attempt of ``case_id`` in an isolated clone. Always tears down."""
    clone = Path(tempfile.mkdtemp(prefix=f"eval-{run_id}-{case_id}-"))
    try:
        subprocess.run(
            ["git", "clone", "--local", str(repo), str(clone)],
            check=True, capture_output=True, text=True,
        )
        spec = clone / "evals" / "cases" / case_id / "spec.md"
        subprocess.run(
            ["python3", _INIT, "init", "--spec", str(spec), "--force",
             "--max-workers", "2"],
            cwd=str(clone), check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["python3", _LOOP, "--max-iter", str(max_iter),
             "--max-cost-usd", str(max_cost_usd)],
            cwd=str(clone),
            check=False,  # non-zero exit is expected (budget-cap, pivot-needed); oracle decides pass/fail
            capture_output=True, text=True,
        )
        run = _read_run_result(clone)
        oracle = load_case_oracle(case_id)
        return oracle(clone, run)
    except Exception as exc:  # any failure, including the oracle, is bucketed as error
        return OracleResult(outcome="error", reason=f"{type(exc).__name__}: {exc}")
    finally:
        _teardown(clone)


def _read_run_result(clone: Path) -> RunResult:
    """Best-effort RunResult from the clone's state.json (cost/budget deferred to cut-2)."""
    state_path = clone / ".planning" / "auto-pilot" / "state.json"
    status = "failed"
    iters = 0
    if state_path.exists():
        data = json.loads(state_path.read_text())
        status = str(data.get("status", "failed"))
        iters = int(data.get("iter", 0) or 0)
    return RunResult(
        returncode=0,
        status=status,
        state_path=state_path,
        cost_usd=0.0,  # cut-1: cost attribution deferred (best-effort, see spec)
        iters=iters,
        log_dir=clone,
        workdir=clone,
    )


def _teardown(clone: Path) -> None:
    shutil.rmtree(clone, ignore_errors=True)
