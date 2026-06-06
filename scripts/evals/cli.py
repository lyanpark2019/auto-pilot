"""`python3 scripts/evals/cli.py run --tier smoke` — cut-1 advisory eval runner."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Run-as-file bootstrap: put the harness `scripts/` dir on sys.path so the
# `evals.*` imports below resolve when invoked as `python3 scripts/evals/cli.py`
# (outside pytest, where tests/conftest.py would otherwise add it).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.aggregate import select_cases, summarize, write_results  # noqa: E402
from evals.regress import compare  # noqa: E402
from evals.runner import run_case  # noqa: E402

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
    # Baseline is a run-level constant; read once and tolerate its absence
    # (the CLI may run before any baseline has been committed).
    baseline_cases: dict[str, Any] = {}
    if _BASELINE.exists():
        baseline_cases = json.loads(_BASELINE.read_text()).get("cases", {})
    summaries: list[dict[str, Any]] = []
    for cid in case_ids:
        attempts = [run_case(cid, run_id="local") for _ in range(args.repeats)]
        s = summarize(cid, attempts)
        summaries.append(s)
        baseline = baseline_cases.get(cid)
        if baseline:
            verdict = compare(
                {"passed": s["passed"], "attempts": s["attempts"], "errored": s["errored"]},
                baseline, cut1=True,
            )
            print(f"{cid}: {s['passed']}/{s['attempts']} pass "
                  f"(advisory armed={verdict['armed']} would_fire={verdict['would_fire']} "
                  f"error_spike={verdict['error_spike']})")
    write_results(Path(args.out), "local", summaries)
    return 0  # cut-1 is advisory: always exit 0


if __name__ == "__main__":
    raise SystemExit(main())
