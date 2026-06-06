#!/usr/bin/env python3
"""Cost telemetry: accumulate worker token usage per PM round.

Each worker dispatch should call:
    tracker.record(round_num, worker_type, usage_dict)
where usage_dict has keys input_tokens, output_tokens, cache_read_input_tokens,
cache_creation_input_tokens, total_tokens.

PM loop calls tracker.over_budget(round_num) before issuing new tickets.
Abort if rubric.yaml budget exceeded.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PATH = PLUGIN_ROOT / "templates" / "rubric.yaml"

# Default per-1M token prices (USD). Override via env or rubric.yaml.
DEFAULT_PRICES = {
    "opus": {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_write": 18.75},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
    "haiku": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_write": 1.0},
}


def _data_dir(vault: Path) -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        d = Path(env) / "vault-builder"
    else:
        d = vault / "meta" / "_cost"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_rubric() -> dict[str, Any]:
    if yaml is None or not RUBRIC_PATH.exists():
        return {}
    try:
        return yaml.safe_load(RUBRIC_PATH.read_text()) or {}
    except Exception:
        return {}


class CostTracker:
    def __init__(self, vault: Path):
        self.vault = vault
        self.log_path = _data_dir(vault) / "cost-log.jsonl"
        self.rubric = _load_rubric()
        budget = (self.rubric.get("cost") or {})
        self.mode = budget.get("mode", "subscription")
        self.max_total_usd = float(budget.get("max_total_usd", 50.0))
        self.max_round_usd = float(budget.get("max_round_usd", 10.0))

    def record(
        self,
        round_num: int,
        worker_type: str,
        usage: dict[str, int],
        model: str = "sonnet",
        ticket_id: str | None = None,
    ) -> dict[str, Any]:
        prices = DEFAULT_PRICES.get(model, DEFAULT_PRICES["sonnet"])
        cost = (
            usage.get("input_tokens", 0) * prices["input"]
            + usage.get("output_tokens", 0) * prices["output"]
            + usage.get("cache_read_input_tokens", 0) * prices["cache_read"]
            + usage.get("cache_creation_input_tokens", 0) * prices["cache_write"]
        ) / 1_000_000
        entry = {
            "ts": time.time(),
            "round": round_num,
            "worker": worker_type,
            "ticket_id": ticket_id,
            "model": model,
            "usage": usage,
            "cost_usd": round(cost, 6),
        }
        with self.log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def round_cost(self, round_num: int) -> float:
        return sum(e["cost_usd"] for e in self._iter() if e["round"] == round_num)

    def total_cost(self) -> float:
        return sum(e["cost_usd"] for e in self._iter())

    def over_budget(self, round_num: int) -> tuple[bool, str]:
        if self.mode == "subscription":
            return False, "subscription mode — quota tracked by Claude Code, no $ gate"
        rc = self.round_cost(round_num)
        tc = self.total_cost()
        if tc >= self.max_total_usd:
            return True, f"total ${tc:.2f} ≥ cap ${self.max_total_usd:.2f}"
        if rc >= self.max_round_usd:
            return True, f"round {round_num} ${rc:.2f} ≥ cap ${self.max_round_usd:.2f}"
        return False, f"ok: round ${rc:.2f} / total ${tc:.2f}"

    def report(self) -> dict[str, Any]:
        per_worker: dict[str, float] = {}
        per_round: dict[int, float] = {}
        for e in self._iter():
            per_worker[e["worker"]] = per_worker.get(e["worker"], 0) + e["cost_usd"]
            per_round[e["round"]] = per_round.get(e["round"], 0) + e["cost_usd"]
        return {
            "total_usd": round(self.total_cost(), 4),
            "per_worker": {k: round(v, 4) for k, v in per_worker.items()},
            "per_round": {k: round(v, 4) for k, v in per_round.items()},
            "budget_total": self.max_total_usd,
            "budget_round": self.max_round_usd,
        }

    def _iter(self):
        if not self.log_path.exists():
            return
        for line in self.log_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: cost_tracker.py <vault_path> [report|round N|check N]", file=sys.stderr)
        return 1
    vault = Path(argv[1]).expanduser().resolve()
    tracker = CostTracker(vault)
    cmd = argv[2] if len(argv) > 2 else "report"

    if cmd == "report":
        print(json.dumps(tracker.report(), indent=2))
    elif cmd == "round" and len(argv) > 3:
        print(json.dumps({"round": int(argv[3]), "cost_usd": tracker.round_cost(int(argv[3]))}, indent=2))
    elif cmd == "check" and len(argv) > 3:
        over, msg = tracker.over_budget(int(argv[3]))
        print(json.dumps({"over_budget": over, "msg": msg}, indent=2))
        return 2 if over else 0
    else:
        print(f"unknown cmd: {cmd}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
