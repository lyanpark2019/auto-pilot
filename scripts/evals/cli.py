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

from _log import event  # noqa: E402
from evals.aggregate import select_cases, summarize, write_results  # noqa: E402
from evals.regress import compare  # noqa: E402
from evals.runner import run_case  # noqa: E402

_REPO = Path(__file__).resolve().parent.parent.parent
_CASES = _REPO / "evals" / "cases"
_BASELINE = _REPO / "evals" / "baseline.json"
_MAX_TOTAL_COST_USD = 50.0  # matches _config.default_max_cost_usd


def _emit(message: str) -> None:
    sys.stdout.write(f"{message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evals")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--tier", default="smoke")
    run.add_argument("--case", default=None)
    run.add_argument("--repeats", type=int, default=5)
    run.add_argument("--out", default=str(_REPO / "evals" / "results" / "local.json"))
    run.add_argument("--max-total-cost-usd", type=float, default=_MAX_TOTAL_COST_USD)
    return parser


def _load_baseline_cases() -> dict[str, Any]:
    if not _BASELINE.exists():
        return {}
    try:
        data = json.loads(_BASELINE.read_text())
    except json.JSONDecodeError:
        event("eval_cli.baseline_malformed", error_type="JSONDecodeError")
        _emit("warning: baseline.json is malformed — running without a baseline (advisory)")
        return {}
    cases = data.get("cases", {})
    return cases if isinstance(cases, dict) else {}


def _run_case_repeats(cid: str, repeats: int, baseline: dict[str, Any] | None) -> tuple[dict[str, Any], float]:
    event("eval_cli.case_start", case_id=cid, repeats=repeats)
    attempts = [run_case(cid, run_id="local") for _ in range(repeats)]
    summary = summarize(cid, attempts)
    if baseline:
        verdict = compare(
            {"passed": summary["passed"], "attempts": summary["attempts"], "errored": summary["errored"]},
            baseline, cut1=True,
        )
        event("eval_cli.baseline_compare", case_id=cid, armed=verdict["armed"], would_fire=verdict["would_fire"])
        _emit(f"{cid}: {summary['passed']}/{summary['attempts']} pass "
              f"(advisory armed={verdict['armed']} would_fire={verdict['would_fire']} "
              f"error_spike={verdict['error_spike']})")
    return summary, sum(attempt.run.cost_usd for attempt in attempts)


def _run_selected_cases(args: argparse.Namespace, case_ids: list[str], baseline_cases: dict[str, Any]) -> tuple[list[dict[str, Any]], float, bool]:
    summaries: list[dict[str, Any]] = []
    total_cost = 0.0
    stopped_early = False
    for cid in case_ids:
        if total_cost > args.max_total_cost_usd:
            event("eval_cli.cost_ceiling", total_cost_usd=round(total_cost, 4), case_id=cid)
            _emit(f"total-cost ceiling ${args.max_total_cost_usd:.2f} exceeded (${total_cost:.2f}) — stopping before {cid}")
            stopped_early = True
            break
        summary, cost = _run_case_repeats(cid, args.repeats, baseline_cases.get(cid))
        total_cost += cost
        summaries.append(summary)
    return summaries, total_cost, stopped_early


def main(argv: list[str] | None = None) -> int:
    """Run the cli command-line entry point."""
    args = _build_parser().parse_args(argv)
    case_ids = [args.case] if args.case else select_cases(_CASES, args.tier)
    summaries, total_cost, stopped_early = _run_selected_cases(args, case_ids, _load_baseline_cases())
    event("eval_cli.done", cases=len(case_ids), total_cost_usd=round(total_cost, 4), stopped_early=stopped_early)
    write_results(
        Path(args.out), "local", summaries,
        meta={"total_cost_usd": round(total_cost, 4), "stopped_early": stopped_early},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
