"""Per-case attempt runner: isolate via a fresh clone, run auto-pilot headless,
then the case oracle. Teardown is in a ``finally`` (round-3 P2-D)."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from evals._types import CaseAttempt, OracleResult, RunResult
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
) -> CaseAttempt:
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
        return CaseAttempt(oracle(clone, run), run)
    except Exception as exc:  # any failure, including the oracle, is bucketed as error
        # paths in the error RunResult are nominal — `clone` is torn down in `finally`
        return CaseAttempt(
            OracleResult(outcome="error", reason=f"{type(exc).__name__}: {exc}"),
            _null_run_result(clone),
        )
    finally:
        _teardown(clone)


def _read_run_result(clone: Path) -> RunResult:
    """Best-effort RunResult from the clone's state.json (cost read in cut-2.1)."""
    state_path = clone / ".planning" / "auto-pilot" / "state.json"
    status = "failed"
    iters = 0
    cost = 0.0
    if state_path.exists():
        data = json.loads(state_path.read_text())
        status = str(data.get("status", "failed"))
        iters = int(data.get("iter", 0) or 0)
        cost = float(data.get("cost_usd", 0.0) or 0.0)
    return RunResult(
        returncode=0, status=status, state_path=state_path,
        cost_usd=cost, iters=iters, log_dir=clone, workdir=clone,
    )


def _null_run_result(path: Path) -> RunResult:
    """Zero-cost error-bucket RunResult for attempts that never produced state."""
    return RunResult(
        returncode=2, status="error",
        state_path=path / ".planning" / "auto-pilot" / "state.json",
        cost_usd=0.0, iters=0, log_dir=path, workdir=path,
    )


def _teardown(clone: Path) -> None:
    shutil.rmtree(clone, ignore_errors=True)
