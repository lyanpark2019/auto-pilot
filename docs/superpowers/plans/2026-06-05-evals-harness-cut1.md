# Evals Harness — Cut 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the cut-1 evals harness for auto-pilot — prove the clone→init→loop→oracle plumbing on one real case, with a fully-tested deterministic statistics core — without arming any blocking gate.

**Architecture:** Pure-Python package `scripts/evals/`. A per-case runner clones the repo (`git clone --local`), runs auto-pilot headless on a case spec, then a deterministic per-case `oracle.py` asserts the spec's deliverable. A stdlib (no scipy) Newcombe/Wilson difference-interval decides regression; in cut-1 it is **advisory only** (never `exit≠0`). The harness-health gate (existing `dogfood_tier1`) is untouched. Tests under `tests/` run in the existing per-PR CI `pytest` gate.

**Tech Stack:** Python 3 stdlib (`math`, `subprocess`, `dataclasses`, `json`, `pathlib`), pytest. No new dependencies. Reuses `scripts/_budget.parse_session_usage`, `scripts/orchestrator.py init`, `scripts/headless-loop.py`.

**Spec:** `docs/superpowers/specs/2026-06-05-evals-harness-design.md` (merged, APPROVED). This plan implements **cut 1 only**; cut-2 items (`fingerprint.py`, `promote.py`, `history.jsonl`, the `eval promote` command, blocking-gate arming) are explicitly out of scope.

---

## File structure (cut 1)

```
scripts/evals/
  __init__.py        # empty package marker
  _types.py          # RunResult, OracleResult (frozen dataclasses)
  stats.py           # Wilson + Newcombe difference interval + is_regression
  oracle_api.py      # OracleProtocol + load_case_oracle + run_verify_cmds helper
  runner.py          # per-case: clone → init → loop → oracle (subprocess-driven)
  aggregate.py       # corpus selection + aggregate + results JSON
  regress.py         # compare run vs baseline (cut-1: advisory, never exit!=0)
  cli.py             # `python -m scripts.evals.cli run --tier smoke [--case ID]`
evals/
  cases/dogfood-smoke/
    spec.md          # the case task (points at the dogfood smoke spec)
    oracle.py        # task-success oracle: runs the smoke spec's two Verify cmds
    meta.json        # {tags, expected_phases, added_from}
  baseline.json      # hand-written cut-1 baseline
  _fixtures/
    good/scripts/_dogfood_noop.py        # correct deliverable (passes oracle)
    good/tests/test_dogfood_noop.py
    broken/scripts/_dogfood_noop.py      # wrong deliverable (fails oracle)
    broken/tests/test_dogfood_noop.py
commands/
  eval-run.md        # thin slash command → cli.py
tests/
  test_evals_stats.py    # boundary table tests (pin reviewer-verified numbers)
  test_evals_oracle.py   # meta-test: oracle passes good fixture, fails broken
  test_evals_runner.py   # clone/init/loop sequence + finally-teardown (mocked)
  test_evals_aggregate.py
  test_evals_regress.py
```

`mypy` checks `scripts/` only, so everything under `scripts/evals/` is type-gated; `evals/cases/*/oracle.py` and `evals/_fixtures/` are data/fixtures, not type-gated. Keep every file < 500 lines (CI `check-module-size.sh`).

---

## Task 1: Scaffold package + value types

**Files:**
- Create: `scripts/evals/__init__.py`
- Create: `scripts/evals/_types.py`
- Test: `tests/test_evals_stats.py` (placeholder import — extended in Task 2)

- [ ] **Step 1: Create the empty package marker**

Create `scripts/evals/__init__.py` with a single line:

```python
"""Evals harness (cut 1): deterministic task-success measurement for auto-pilot."""
```

- [ ] **Step 2: Write the failing test for the value types**

Create `tests/test_evals_stats.py`:

```python
from pathlib import Path

from scripts.evals._types import OracleResult, RunResult


def test_run_result_and_oracle_result_construct() -> None:
    rr = RunResult(
        returncode=0,
        status="success",
        state_path=Path(".planning/auto-pilot/state.json"),
        cost_usd=1.23,
        iters=2,
        log_dir=Path("/tmp/logs"),
        workdir=Path("/tmp/clone"),
    )
    assert rr.status == "success"
    ok = OracleResult(outcome="pass", reason="")
    assert ok.outcome == "pass"
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/test_evals_stats.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.evals._types'`

- [ ] **Step 4: Implement the types**

Create `scripts/evals/_types.py`:

```python
"""Value types handed to every case oracle. The one interface case authors touch."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Terminal state.json statuses (headless-loop.py:200). Non-"success" => non-pass.
TERMINAL_STATUSES = frozenset(
    {"success", "stopped", "pivot-needed", "failed", "cost-cap"}
)


@dataclass(frozen=True)
class RunResult:
    """What the runner produces per case attempt."""

    returncode: int  # headless-loop exit code (0 ok, 2 = no state, 124 = timeout)
    status: str  # final state.json status; one of TERMINAL_STATUSES
    state_path: Path  # the run's .planning/auto-pilot/state.json
    cost_usd: float  # best-effort (_budget.parse_session_usage; may be an estimate)
    iters: int
    log_dir: Path
    workdir: Path  # the case clone root


@dataclass(frozen=True)
class OracleResult:
    """Deterministic per-case verdict. outcome in {pass, fail, error}."""

    outcome: str
    reason: str  # required for fail/error; "" for pass
```

- [ ] **Step 5: Run it to verify it passes**

Run: `python -m pytest tests/test_evals_stats.py -q`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add scripts/evals/__init__.py scripts/evals/_types.py tests/test_evals_stats.py
git commit -m "feat(evals): scaffold package + RunResult/OracleResult value types"
```

---

## Task 2: Statistics core (the highest-risk, fully TDD)

The spec's regression rule: `FAIL iff upper95(p_new − p_base) < −margin` (margin 0.05), using a Newcombe (method-10) difference interval built from two Wilson score intervals, z=1.96. The four reviewer-verified boundary numbers are pinned as tests.

**Files:**
- Create: `scripts/evals/stats.py`
- Test: `tests/test_evals_stats.py` (extend)

- [ ] **Step 1: Write the failing boundary tests**

Append to `tests/test_evals_stats.py`:

```python
from scripts.evals.stats import diff_upper, is_regression


def test_wilson_diff_upper_matches_reviewer_numbers() -> None:
    # regression: new 76/100 vs baseline 100/100 -> upper ~ -0.158 (fires)
    assert round(diff_upper(76, 100, 100, 100), 3) == -0.158
    # noise: 99/100 vs 100/100 -> upper ~ +0.028 (passes)
    assert diff_upper(99, 100, 100, 100) > -0.05
    # improvement: 100/100 vs 95/100 -> positive, never fires
    assert diff_upper(100, 100, 95, 100) > 0


def test_arming_and_mde_boundary() -> None:
    # below arm floor (A < 50): advisory regardless
    armed, failed = is_regression(0, 5, 1000, 1000)
    assert armed is False and failed is False
    # at A=50 with gated baseline ~1.0 (C*B*K = 1000): MDE boundary
    armed, failed = is_regression(44, 50, 1000, 1000)  # -0.056 < -0.05
    assert armed is True and failed is True
    armed, failed = is_regression(45, 50, 1000, 1000)  # -0.043 >= -0.05
    assert armed is True and failed is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_evals_stats.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.evals.stats'`

- [ ] **Step 3: Implement the stats**

Create `scripts/evals/stats.py`:

```python
"""Deterministic regression statistics — stdlib only (no scipy/numpy).

Newcombe (method-10) confidence interval for the difference of two proportions,
each estimated by a Wilson score interval. Used by regress.py. The gate fires
when the upper bound of (p_new - p_base) drops below -margin: i.e. we are
confident the new run is worse by more than the margin.
"""
from __future__ import annotations

import math

Z95 = 1.96  # two-sided 95%
DEFAULT_MARGIN = 0.05
DEFAULT_ARM_MIN = 50


def _wilson(x: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval ``(lower, upper)`` for x successes in n trials."""
    if n == 0:
        return (0.0, 1.0)
    p = x / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return (center - half, center + half)


def diff_upper(
    x_new: int, n_new: int, x_base: int, n_base: int, z: float = Z95
) -> float:
    """Newcombe method-10 upper bound of ``(p_new - p_base)``."""
    p1, p2 = x_new / n_new, x_base / n_base
    l1, u1 = _wilson(x_new, n_new, z)
    l2, u2 = _wilson(x_base, n_base, z)
    return (p1 - p2) + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def is_regression(
    x_new: int,
    n_new: int,
    x_base: int,
    n_base: int,
    margin: float = DEFAULT_MARGIN,
    arm_min: int = DEFAULT_ARM_MIN,
) -> tuple[bool, bool]:
    """Return ``(armed, failed)``.

    ``armed`` is False (advisory) when ``n_new < arm_min``; ``failed`` can only be
    True when armed. A run is a regression when the difference-interval upper bound
    is below ``-margin``.
    """
    armed = n_new >= arm_min
    failed = armed and diff_upper(x_new, n_new, x_base, n_base) < -margin
    return armed, failed
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_evals_stats.py -q`
Expected: PASS (3 passed). If the `-0.158` exact-round assertion is off by float noise, confirm z=1.96 and the Newcombe formula; do **not** weaken the boundary tests.

- [ ] **Step 5: Typecheck + lint**

Run: `python -m mypy scripts/evals/stats.py && python -m ruff check scripts/evals/`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/evals/stats.py tests/test_evals_stats.py
git commit -m "feat(evals): Newcombe/Wilson difference-interval regression stats (stdlib)"
```

---

## Task 3: Oracle contract + dogfood case oracle + meta-test fixtures

The task-success oracle asserts the *deliverable*, never auto-pilot internals. The dogfood case runs the smoke spec's two Verify cmds inside the workdir clone. The meta-test proves the oracle passes a good fixture and fails a broken one — and runs in CI with **no agent runs**.

**Files:**
- Create: `scripts/evals/oracle_api.py`
- Create: `evals/cases/dogfood-smoke/oracle.py`
- Create: `evals/_fixtures/good/scripts/_dogfood_noop.py`
- Create: `evals/_fixtures/good/tests/test_dogfood_noop.py`
- Create: `evals/_fixtures/broken/scripts/_dogfood_noop.py`
- Create: `evals/_fixtures/broken/tests/test_dogfood_noop.py`
- Test: `tests/test_evals_oracle.py`

- [ ] **Step 1: Create the good + broken fixtures**

`evals/_fixtures/good/scripts/_dogfood_noop.py`:

```python
def dogfood_identity(x: int) -> int:
    return x
```

`evals/_fixtures/good/tests/test_dogfood_noop.py`:

```python
from scripts._dogfood_noop import dogfood_identity


def test_identity() -> None:
    assert dogfood_identity(7) == 7
```

`evals/_fixtures/broken/scripts/_dogfood_noop.py` (off-by-one → Verify cmd assertion fails):

```python
def dogfood_identity(x: int) -> int:
    return x + 1
```

`evals/_fixtures/broken/tests/test_dogfood_noop.py` (same test; will fail against the broken impl):

```python
from scripts._dogfood_noop import dogfood_identity


def test_identity() -> None:
    assert dogfood_identity(7) == 7
```

Add empty `evals/_fixtures/good/scripts/__init__.py`, `.../good/tests/__init__.py` and the broken equivalents so `scripts._dogfood_noop` imports cleanly when the workdir root is on `sys.path`.

- [ ] **Step 2: Write the failing meta-test**

Create `tests/test_evals_oracle.py`:

```python
from pathlib import Path

from scripts.evals._types import RunResult

FIXTURES = Path(__file__).resolve().parent.parent / "evals" / "_fixtures"


def _run_result(workdir: Path) -> RunResult:
    return RunResult(
        returncode=0,
        status="success",
        state_path=workdir / ".planning/auto-pilot/state.json",
        cost_usd=0.0,
        iters=1,
        log_dir=workdir,
        workdir=workdir,
    )


def test_oracle_passes_good_fixture() -> None:
    from scripts.evals.oracle_api import load_case_oracle

    check = load_case_oracle("dogfood-smoke")
    good = FIXTURES / "good"
    res = check(good, _run_result(good))
    assert res.outcome == "pass", res.reason


def test_oracle_fails_broken_fixture() -> None:
    from scripts.evals.oracle_api import load_case_oracle

    check = load_case_oracle("dogfood-smoke")
    broken = FIXTURES / "broken"
    res = check(broken, _run_result(broken))
    assert res.outcome == "fail", res.reason
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/test_evals_oracle.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.evals.oracle_api'`

- [ ] **Step 4: Implement the oracle API + dogfood oracle**

Create `scripts/evals/oracle_api.py`:

```python
"""General per-case oracle contract + helpers.

A case ``oracle.py`` exports ``check(workdir, run) -> OracleResult``. This module
loads it and offers a deterministic shell-command verifier. It does NOT wrap
``_dogfood_gate`` (that is the separate harness-health gate, Gate 2).
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Callable

from scripts.evals._types import OracleResult, RunResult

CheckFn = Callable[[Path, RunResult], OracleResult]

_CASES_DIR = Path(__file__).resolve().parent.parent.parent / "evals" / "cases"


def load_case_oracle(case_id: str) -> CheckFn:
    """Import ``evals/cases/<case_id>/oracle.py`` and return its ``check``."""
    path = _CASES_DIR / case_id / "oracle.py"
    spec = importlib.util.spec_from_file_location(f"evals_case_{case_id}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load oracle at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check  # type: ignore[no-any-return]


def run_verify_cmd(workdir: Path, cmd: str, timeout: int = 120) -> tuple[bool, str]:
    """Run a shell Verify cmd in ``workdir``; return ``(ok, detail)``.

    ``workdir`` is put on PYTHONPATH so ``from scripts.x import ...`` resolves
    against the case clone, not the harness repo.
    """
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(workdir),
            env={"PYTHONPATH": str(workdir), "PATH": _safe_path()},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (False, f"timeout after {timeout}s: {cmd}")
    detail = (proc.stdout + proc.stderr).strip()[-500:]
    return (proc.returncode == 0, detail)


def _safe_path() -> str:
    import os

    return os.environ.get("PATH", "/usr/bin:/bin")
```

Create `evals/cases/dogfood-smoke/oracle.py`:

```python
"""Task-success oracle for the dogfood smoke case.

Asserts the deliverable via the smoke spec's two Verify cmds. Producer-agnostic:
never reads .planning/auto-pilot internals.
"""
from __future__ import annotations

from pathlib import Path

import sys

# Allow running both in-tree (pytest) and as a loaded module file.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.evals._types import OracleResult, RunResult  # noqa: E402
from scripts.evals.oracle_api import run_verify_cmd  # noqa: E402

VERIFY_CMDS = (
    'python3 -c "from scripts._dogfood_noop import dogfood_identity; '
    'assert dogfood_identity(7) == 7"',
    "python3 -m pytest -q tests/test_dogfood_noop.py",
)


def check(workdir: Path, run: RunResult) -> OracleResult:
    for cmd in VERIFY_CMDS:
        ok, detail = run_verify_cmd(workdir, cmd)
        if not ok:
            return OracleResult(outcome="fail", reason=f"{cmd} -> {detail}")
    return OracleResult(outcome="pass", reason="")
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest tests/test_evals_oracle.py -q`
Expected: PASS (2 passed). The good fixture's two Verify cmds exit 0; the broken fixture's first Verify cmd assertion fails → `outcome == "fail"`.

- [ ] **Step 6: Create `meta.json` + `spec.md` for the case**

`evals/cases/dogfood-smoke/meta.json`:

```json
{
  "tags": ["smoke"],
  "expected_phases": 2,
  "added_from": "dogfood",
  "spec_source": "docs/specs/2026-05-28-dogfood-smoke.md"
}
```

`evals/cases/dogfood-smoke/spec.md`: copy the contents of `docs/specs/2026-05-28-dogfood-smoke.md` verbatim (the runner feeds this to `orchestrator.py init --spec`). Keep it as a real copy, not a symlink (the clone must contain it).

- [ ] **Step 7: Typecheck + lint + commit**

Run: `python -m mypy scripts/evals/oracle_api.py && python -m ruff check scripts/evals/ tests/test_evals_oracle.py`
Expected: clean.

```bash
git add scripts/evals/oracle_api.py evals/cases/ evals/_fixtures/ tests/test_evals_oracle.py
git commit -m "feat(evals): oracle contract + dogfood task-success oracle + meta-test fixtures"
```

---

## Task 4: Per-case runner (clone → init → loop → oracle, teardown in finally)

The runner orchestrates one attempt. Real agent invocation is slow/costly, so the **unit test mocks `subprocess.run` and the oracle**, asserting the exact command sequence and that teardown fires on every path (`finally`).

**Files:**
- Create: `scripts/evals/runner.py`
- Test: `tests/test_evals_runner.py`

- [ ] **Step 1: Write the failing test (command sequence + finally teardown)**

Create `tests/test_evals_runner.py`:

```python
from pathlib import Path
from unittest import mock

from scripts.evals._types import OracleResult


def test_run_case_sequence_and_teardown(tmp_path: Path) -> None:
    from scripts.evals import runner

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(cmd if isinstance(cmd, list) else [cmd])
        return mock.Mock(returncode=0, stdout="", stderr="")

    teardown_seen: list[Path] = []

    with mock.patch("scripts.evals.runner.subprocess.run", side_effect=fake_run), \
        mock.patch(
            "scripts.evals.runner._read_run_result",
            return_value=mock.Mock(status="success"),
        ), \
        mock.patch(
            "scripts.evals.runner.load_case_oracle",
            return_value=lambda wd, rr: OracleResult("pass", ""),
        ), \
        mock.patch(
            "scripts.evals.runner._teardown",
            side_effect=lambda p: teardown_seen.append(p),
        ):
        res = runner.run_case("dogfood-smoke", repo=tmp_path, run_id="r1")

    assert res.outcome == "pass"
    # clone, then orchestrator init --spec --force, then headless-loop ran
    joined = " ".join(" ".join(c) for c in calls)
    assert "clone" in joined and "--local" in joined
    assert "orchestrator.py" in joined and "--spec" in joined and "--force" in joined
    assert "headless-loop.py" in joined
    assert len(teardown_seen) == 1  # teardown fired exactly once


def test_run_case_teardown_on_failure(tmp_path: Path) -> None:
    from scripts.evals import runner

    teardown_seen: list[Path] = []
    with mock.patch(
        "scripts.evals.runner.subprocess.run",
        side_effect=RuntimeError("boom"),
    ), mock.patch(
        "scripts.evals.runner._teardown",
        side_effect=lambda p: teardown_seen.append(p),
    ):
        res = runner.run_case("dogfood-smoke", repo=tmp_path, run_id="r1")

    assert res.outcome == "error"
    assert len(teardown_seen) == 1  # teardown still fired on the failure path
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_evals_runner.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.evals.runner'`

- [ ] **Step 3: Implement the runner**

Create `scripts/evals/runner.py`:

```python
"""Per-case attempt runner: isolate via a fresh clone, run auto-pilot headless,
then the case oracle. Teardown is in a ``finally`` (round-3 P2-D)."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.evals._types import OracleResult, RunResult
from scripts.evals.oracle_api import load_case_oracle

_REPO = Path(__file__).resolve().parent.parent.parent
INIT = "scripts/orchestrator.py"
LOOP = "scripts/headless-loop.py"


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
            ["python3", INIT, "init", "--spec", str(spec), "--force",
             "--max-workers", "2"],
            cwd=str(clone), check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["python3", LOOP, "--max-iter", str(max_iter),
             "--max-cost-usd", str(max_cost_usd)],
            cwd=str(clone), check=False, capture_output=True, text=True,
        )
        run = _read_run_result(clone)
        check = load_case_oracle(case_id)
        return check(clone, run)
    except Exception as exc:  # noqa: BLE001 - any failure before oracle = error bucket
        return OracleResult(outcome="error", reason=f"{type(exc).__name__}: {exc}")
    finally:
        _teardown(clone)


def _read_run_result(clone: Path) -> RunResult:
    """Best-effort RunResult from the clone's state.json + budget log."""
    import json

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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_evals_runner.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Typecheck + lint + commit**

Run: `python -m mypy scripts/evals/runner.py && python -m ruff check scripts/evals/ tests/test_evals_runner.py`
Expected: clean.

```bash
git add scripts/evals/runner.py tests/test_evals_runner.py
git commit -m "feat(evals): per-case runner (clone/init/loop/oracle) with finally teardown"
```

---

## Task 5: Corpus selection + aggregation + results JSON

**Files:**
- Create: `scripts/evals/aggregate.py`
- Test: `tests/test_evals_aggregate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_evals_aggregate.py`:

```python
import json
from pathlib import Path

from scripts.evals._types import OracleResult


def test_select_cases_by_tier(tmp_path: Path) -> None:
    from scripts.evals import aggregate

    cases = tmp_path / "cases"
    (cases / "a").mkdir(parents=True)
    (cases / "a" / "meta.json").write_text(json.dumps({"tags": ["smoke"]}))
    (cases / "b").mkdir()
    (cases / "b" / "meta.json").write_text(json.dumps({"tags": ["full"]}))

    assert aggregate.select_cases(cases, tier="smoke") == ["a"]
    assert sorted(aggregate.select_cases(cases, tier="full")) == ["a", "b"]


def test_aggregate_counts() -> None:
    from scripts.evals import aggregate

    results = [
        OracleResult("pass", ""),
        OracleResult("pass", ""),
        OracleResult("fail", "x"),
        OracleResult("error", "boom"),
    ]
    summary = aggregate.summarize("dogfood-smoke", results)
    assert summary["passed"] == 2
    assert summary["failed"] == 1
    assert summary["errored"] == 1
    assert summary["attempts"] == 4  # error counts toward total_attempted
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_evals_aggregate.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement aggregate**

Create `scripts/evals/aggregate.py`:

```python
"""Corpus selection + aggregation of OracleResults into a results summary."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.evals._types import OracleResult


def select_cases(cases_dir: Path, tier: str) -> list[str]:
    """Return case ids whose meta tags include ``tier`` (``full`` selects all)."""
    out: list[str] = []
    for meta_path in sorted(cases_dir.glob("*/meta.json")):
        tags = set(json.loads(meta_path.read_text()).get("tags", []))
        if tier == "full" or tier in tags:
            out.append(meta_path.parent.name)
    return out


def summarize(case_id: str, results: list[OracleResult]) -> dict[str, Any]:
    """Aggregate per-case results. error counts toward total_attempted (non-pass)."""
    passed = sum(1 for r in results if r.outcome == "pass")
    failed = sum(1 for r in results if r.outcome == "fail")
    errored = sum(1 for r in results if r.outcome == "error")
    attempts = len(results)
    return {
        "case": case_id,
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "attempts": attempts,
        "pass_rate": (passed / attempts) if attempts else 0.0,
        "reasons": [r.reason for r in results if r.outcome != "pass"],
    }


def write_results(path: Path, run_id: str, summaries: list[dict[str, Any]]) -> None:
    payload = {"run_id": run_id, "cases": summaries}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_evals_aggregate.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Typecheck + lint + commit**

Run: `python -m mypy scripts/evals/aggregate.py && python -m ruff check scripts/evals/ tests/test_evals_aggregate.py`

```bash
git add scripts/evals/aggregate.py tests/test_evals_aggregate.py
git commit -m "feat(evals): corpus selection + result aggregation + results JSON"
```

---

## Task 6: regress.py — advisory comparison (cut-1: never exit≠0)

**Files:**
- Create: `scripts/evals/regress.py`
- Create: `evals/baseline.json`
- Test: `tests/test_evals_regress.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_evals_regress.py`:

```python
from scripts.evals.regress import compare


def test_compare_advisory_below_arm_floor() -> None:
    # cut-1: 1 case * K=5 = 5 attempts, below arm floor -> advisory, blocking False
    verdict = compare(
        new={"passed": 4, "attempts": 5, "errored": 0},
        baseline={"passed": 1000, "attempts": 1000, "errored": 0},
        cut1=True,
    )
    assert verdict["armed"] is False
    assert verdict["blocking"] is False  # cut-1 never blocks


def test_compare_reports_regression_advisory_even_when_would_fire() -> None:
    verdict = compare(
        new={"passed": 40, "attempts": 50, "errored": 0},
        baseline={"passed": 1000, "attempts": 1000, "errored": 0},
        cut1=True,
    )
    assert verdict["would_fire"] is True   # statistically a drop
    assert verdict["blocking"] is False    # but cut-1 is advisory by construction
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_evals_regress.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement regress**

Create `scripts/evals/regress.py`:

```python
"""Compare an eval run against a blessed baseline.

CUT 1: advisory by construction — ``blocking`` is always False (the rate gate
arms in cut 2). We still compute ``would_fire`` so the advisory report is honest.
"""
from __future__ import annotations

from typing import Any

from scripts.evals.stats import is_regression


def compare(
    new: dict[str, Any],
    baseline: dict[str, Any],
    margin: float = 0.05,
    cut1: bool = True,
) -> dict[str, Any]:
    armed, failed = is_regression(
        new["passed"], new["attempts"],
        baseline["passed"], baseline["attempts"],
        margin=margin,
    )
    error_spike = new.get("errored", 0) > baseline.get("errored", 0)
    would_fire = bool(failed or error_spike)
    blocking = False if cut1 else (armed and would_fire)
    return {
        "armed": armed,
        "would_fire": would_fire,
        "error_spike": error_spike,
        "blocking": blocking,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_evals_regress.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Hand-write the cut-1 baseline**

Create `evals/baseline.json`:

```json
{
  "note": "Cut-1 hand-written baseline. Advisory only (A<50 cannot arm). Replace with a measured baseline (B>=20 per case) in cut 2 before the rate gate becomes blocking.",
  "model": "TODO-record-at-bless-time",
  "cli": "TODO-record-at-bless-time",
  "cases": {
    "dogfood-smoke": {"passed": 5, "attempts": 5, "errored": 0}
  }
}
```

- [ ] **Step 6: Typecheck + lint + commit**

Run: `python -m mypy scripts/evals/regress.py && python -m ruff check scripts/evals/ tests/test_evals_regress.py`

```bash
git add scripts/evals/regress.py evals/baseline.json tests/test_evals_regress.py
git commit -m "feat(evals): advisory regression compare (cut-1 never blocks) + baseline"
```

---

## Task 7: CLI entry point + slash command

**Files:**
- Create: `scripts/evals/cli.py`
- Create: `commands/eval-run.md`
- Test: `tests/test_evals_aggregate.py` (extend with a CLI smoke using a stubbed runner)

- [ ] **Step 1: Write the failing CLI test**

Append to `tests/test_evals_aggregate.py`:

```python
def test_cli_run_smoke_invokes_runner(tmp_path, monkeypatch, capsys):  # type: ignore[no-untyped-def]
    from scripts.evals import cli
    from scripts.evals._types import OracleResult

    monkeypatch.setattr(
        "scripts.evals.cli.run_case",
        lambda case_id, **kw: OracleResult("pass", ""),
    )
    monkeypatch.setattr("scripts.evals.cli.select_cases", lambda d, tier: ["dogfood-smoke"])

    rc = cli.main(["run", "--tier", "smoke", "--repeats", "1", "--out", str(tmp_path / "r.json")])
    assert rc == 0  # cut-1 advisory: always exit 0
    out = capsys.readouterr().out
    assert "dogfood-smoke" in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest "tests/test_evals_aggregate.py::test_cli_run_smoke_invokes_runner" -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.evals.cli'`.

- [ ] **Step 3: Implement the CLI**

Create `scripts/evals/cli.py`:

```python
"""`python -m scripts.evals.cli run --tier smoke` — cut-1 advisory eval runner."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.evals.aggregate import select_cases, summarize, write_results
from scripts.evals.regress import compare
from scripts.evals.runner import run_case

_REPO = Path(__file__).resolve().parent.parent.parent
_CASES = _REPO / "evals" / "cases"
_BASELINE = _REPO / "evals" / "baseline.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--tier", default="smoke")
    run.add_argument("--case", default=None)
    run.add_argument("--repeats", type=int, default=5)
    run.add_argument("--out", default=str(_REPO / "evals" / "results" / "local.json"))
    args = parser.parse_args(argv)

    case_ids = [args.case] if args.case else select_cases(_CASES, args.tier)
    summaries = []
    for cid in case_ids:
        results = [run_case(cid, run_id="local") for _ in range(args.repeats)]
        s = summarize(cid, results)
        summaries.append(s)
        baseline = json.loads(_BASELINE.read_text())["cases"].get(cid)
        if baseline:
            verdict = compare(
                {"passed": s["passed"], "attempts": s["attempts"], "errored": s["errored"]},
                baseline, cut1=True,
            )
            print(f"{cid}: {s['passed']}/{s['attempts']} pass "
                  f"(advisory armed={verdict['armed']} would_fire={verdict['would_fire']})")
    write_results(Path(args.out), "local", summaries)
    return 0  # cut-1 is advisory: always exit 0
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest "tests/test_evals_aggregate.py::test_cli_run_smoke_invokes_runner" -q`
Expected: PASS.

- [ ] **Step 5: Add the slash command**

Create `commands/eval-run.md`:

```markdown
---
name: eval-run
description: Run the cut-1 evals harness (advisory). Clones the repo per case, runs auto-pilot headless on the case spec, asserts the deliverable with a deterministic oracle, prints an advisory pass-rate vs the blessed baseline. Never blocks (cut-1). Usage `/auto-pilot eval run [--tier smoke|full] [--case ID] [--repeats N]`.
allowed-tools: Bash(python3 -m scripts.evals.cli:*)
---

Run the evals harness in advisory mode:

!`python3 -m scripts.evals.cli run --tier smoke --repeats 1`
```

- [ ] **Step 6: Full suite + typecheck + commit**

Run: `python -m pytest tests/ -q && python -m mypy scripts/ && python -m ruff check scripts/ tests/`
Expected: all green.

```bash
git add scripts/evals/cli.py commands/eval-run.md tests/test_evals_aggregate.py
git commit -m "feat(evals): cut-1 advisory CLI + eval-run slash command"
```

---

## Task 8: Manual smoke + docs wire-up

The unit suite never spawns an agent. This task documents the **one** real end-to-end smoke a human runs once to prove the plumbing, and links the harness from the spec.

**Files:**
- Create: `evals/README.md`
- Modify: `docs/superpowers/specs/2026-06-05-evals-harness-design.md` (add a "cut-1 landed" pointer at the top)

- [ ] **Step 1: Write the evals README (manual smoke procedure)**

Create `evals/README.md`:

```markdown
# Evals harness (cut 1 — advisory)

Cut 1 proves the clone→init→loop→oracle plumbing and the deterministic stats.
It does **not** arm a blocking gate (1 case × K=5 = 5 attempts < the 50 arming
floor; baseline is hand-written). The rate gate arms in cut 2 on a measured baseline.

## Unit gate (per-PR, no agent runs)
`python -m pytest tests/test_evals_*.py -q` — runs in CI's python gate.

## Manual end-to-end smoke (one real agent run; costs ~$1-5, minutes)
```
python3 -m scripts.evals.cli run --case dogfood-smoke --repeats 1
```
Expect: `dogfood-smoke: 1/1 pass (advisory armed=False ...)`. This clones the
repo, runs auto-pilot headless on the dogfood spec, and asserts the deliverable.

## Layers
- Gate 1 (this): task-success rate — advisory in cut 1.
- Gate 2 (unchanged): `scripts/dogfood_tier1.sh` — harness-health, still blocking.
```

- [ ] **Step 2: Add a cut-1 pointer to the spec**

At the top of `docs/superpowers/specs/2026-06-05-evals-harness-design.md`, under the status line, add:

```markdown
> **Cut 1 landed:** `scripts/evals/` + `evals/cases/dogfood-smoke/` + per-PR unit
> gate. Advisory only. See `evals/README.md`. Cut 2 (fingerprint/promote/history/
> blocking gate) not yet started.
```

- [ ] **Step 3: Full verification**

Run: `python -m pytest tests/ -q && python -m mypy scripts/ && python -m ruff check scripts/ tests/ && bash scripts/quality/check-module-size.sh`
Expected: all green; no evals file over 500 lines.

- [ ] **Step 4: Commit**

```bash
git add evals/README.md docs/superpowers/specs/2026-06-05-evals-harness-design.md
git commit -m "docs(evals): cut-1 README (manual smoke) + spec pointer"
```

---

## Out of scope (cut 2 — do NOT build now)

`fingerprint.py` (harness content-hash + model/CLI), `promote.py` + `/auto-pilot eval promote`, `history.jsonl`, the blocking rate gate (arming on a measured B≥20 baseline), generic spec-`Verify cmd` parsing (cut-1 hardcodes the dogfood oracle's two cmds), real cost attribution from `_budget.parse_session_usage`, `max_parallel_clones`/`max_disk_gb` ceilings, and bare-mirror cloning.

## Self-review notes

- Spec coverage: cut-1 scope items (run/oracle_api/stats/one-case/regress/meta-test/clone-isolation/finally-teardown/advisory) each map to Tasks 1–8. Cut-2 items explicitly deferred above.
- Stats numbers (76/100→fires, 99/100→passes, 44/50 vs 45/50 boundary) are pinned as tests and were hand-verified to z=1.96 Newcombe method-10.
- Type consistency: `RunResult`/`OracleResult` (Task 1) used unchanged in Tasks 3–7; `check(workdir, run) -> OracleResult`, `is_regression(...) -> (armed, failed)`, `compare(...) -> dict` signatures are stable across tasks.
