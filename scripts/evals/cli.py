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
_MAX_TOTAL_COST_USD = 50.0  # matches _config.default_max_cost_usd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evals")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--tier", default="smoke")
    run.add_argument("--case", default=None)
    run.add_argument("--repeats", type=int, default=5)
    run.add_argument("--out", default=str(_REPO / "evals" / "results" / "local.json"))
    run.add_argument("--max-total-cost-usd", type=float, default=_MAX_TOTAL_COST_USD)
    args = parser.parse_args(argv)

    case_ids = [args.case] if args.case else select_cases(_CASES, args.tier)

    baseline_cases: dict[str, Any] = {}
    if _BASELINE.exists():
        try:
            baseline_cases = json.loads(_BASELINE.read_text()).get("cases", {})
        except json.JSONDecodeError:
            print("warning: baseline.json is malformed — running without a baseline (advisory)")

    summaries: list[dict[str, Any]] = []
    total_cost = 0.0
    stopped_early = False
    for cid in case_ids:
        if total_cost > args.max_total_cost_usd:
            print(f"total-cost ceiling ${args.max_total_cost_usd:.2f} exceeded "
                  f"(${total_cost:.2f}) — stopping before {cid}")
            stopped_early = True
            break
        attempts = [run_case(cid, run_id="local") for _ in range(args.repeats)]
        total_cost += sum(a.run.cost_usd for a in attempts)
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
    write_results(
        Path(args.out), "local", summaries,
        meta={"total_cost_usd": round(total_cost, 4), "stopped_early": stopped_early},
    )
    return 0  # cut-1/2.1 advisory: always exit 0


if __name__ == "__main__":
    raise SystemExit(main())
