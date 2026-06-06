#!/usr/bin/env python3
"""
PM Loop orchestrator. Wraps ticket_system + score scripts + delta watchdog.

Drives rounds until:
  - structural >= pass_threshold AND
  - content >= pass_threshold AND
  - or max_rounds reached, or delta watchdog triggered

Usage:
    python3 pm_loop.py <vault-path> [--rubric path/to/rubric.yaml]

Note: This is the state machine. Actual worker dispatch is done by the
vault-pm-orchestrator AGENT (uses Agent tool), not by this script directly.
This script provides:
  - score reading
  - gap identification
  - delta watchdog
  - cost tracking placeholders
  - round summary writeback
"""

import json
import os
import sys
import time
from pathlib import Path


def load_rubric(plugin_root: Path):
    rubric_path = plugin_root / "templates" / "rubric.yaml"
    if not rubric_path.exists():
        # safe defaults if pyyaml unavailable
        return {
            "structural": {"pass_threshold": 95},
            "content": {"pass_threshold": 95},
            "safety": {"retry_cap": 3, "max_rounds": 8, "audit_every_n_rounds": 2,
                       "delta_watchdog": {"min_delta": 1.0, "consecutive_rounds": 2}},
        }
    try:
        import yaml
        return yaml.safe_load(rubric_path.read_text())
    except ImportError:
        # parse minimal manually if pyyaml not available
        return {
            "structural": {"pass_threshold": 95},
            "content": {"pass_threshold": 95},
            "safety": {"retry_cap": 3, "max_rounds": 8, "audit_every_n_rounds": 2,
                       "delta_watchdog": {"min_delta": 1.0, "consecutive_rounds": 2}},
        }


def read_scores(vault: Path) -> dict:
    """Read both structural and content score states."""
    out = {"structural": None, "content": None}
    s = vault / "meta" / "score-state.json"
    c = vault / "meta" / "score-content-state.json"
    if s.exists():
        out["structural"] = json.loads(s.read_text())
    if c.exists():
        out["content"] = json.loads(c.read_text())
    return out


def identify_gaps(scores: dict, rubric: dict) -> list:
    """Return list of (axis, dimension, current, max) where current < max."""
    gaps = []
    for axis in ("structural", "content"):
        if not scores.get(axis):
            continue
        dims = rubric.get(axis, {}).get("dimensions", {})
        for dim, val in scores[axis]["scores"].items():
            max_pts = dims.get(dim, {}).get("max", 100)
            if val < max_pts:
                gaps.append({"axis": axis, "dim": dim, "current": val, "max": max_pts})
    return sorted(gaps, key=lambda g: g["max"] - g["current"], reverse=True)


HISTORY_CAP = 200


def delta_watchdog(vault: Path, current_total: float, consecutive: int, min_delta: float) -> bool:
    """Return True if last N rounds delta < min_delta (abort signal)."""
    history_path = vault / "meta" / "pm-score-history.json"
    history = []
    if history_path.exists():
        history = json.loads(history_path.read_text())
    history.append({"at": time.time(), "total": current_total})
    if len(history) > HISTORY_CAP:
        history = history[-HISTORY_CAP:]
    history_path.write_text(json.dumps(history, indent=2))
    if len(history) < consecutive + 1:
        return False
    recent = history[-(consecutive + 1):]
    deltas = [recent[i + 1]["total"] - recent[i]["total"] for i in range(consecutive)]
    return all(abs(d) < min_delta for d in deltas)


def round_summary(round_num: int, scores_before: dict, scores_after: dict, ticket_summary: dict) -> str:
    s_before = scores_before.get("structural", {}).get("total", 0)
    s_after = scores_after.get("structural", {}).get("total", 0)
    c_before = scores_before.get("content", {}).get("total", 0) if scores_before.get("content") else 0
    c_after = scores_after.get("content", {}).get("total", 0) if scores_after.get("content") else 0
    return f"""# PM Round {round_num} Report

## Score deltas
- Structural: {s_before:.1f} → {s_after:.1f} (Δ {s_after - s_before:+.1f})
- Content: {c_before:.1f} → {c_after:.1f} (Δ {c_after - c_before:+.1f})

## Tickets
- Issued: {ticket_summary.get('total', 0)}
- Verified: {ticket_summary.get('by_status', {}).get('verified', 0)}
- Rejected: {ticket_summary.get('by_status', {}).get('rejected', 0)}
- Total reward: {ticket_summary.get('total_reward', 0)}
- Avg retries: {ticket_summary.get('avg_retries', 0):.2f}
"""


def stop_check(scores: dict, rubric: dict) -> tuple[bool, str]:
    s_pass = scores.get("structural", {}).get("total", 0) >= rubric["structural"]["pass_threshold"]
    c_pass = (
        not scores.get("content")
        or scores["content"]["total"] >= rubric["content"]["pass_threshold"]
    )
    if s_pass and c_pass:
        return True, "PASS — both thresholds met"
    return False, f"structural={scores.get('structural',{}).get('total','?')} content={scores.get('content',{}).get('total','?')}"


def main():
    if len(sys.argv) < 2:
        print("Usage: pm_loop.py <vault-path>", file=sys.stderr)
        sys.exit(1)
    vault = Path(sys.argv[1]).expanduser().resolve()
    # Vault-subsystem root: <plugin_root>/vault when CLAUDE_PLUGIN_ROOT is set
    # (vault assets live under vault/ inside the auto-pilot plugin), else
    # anchored to this file's grandparent (= vault/).
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    plugin_root = (Path(env_root) / "vault") if env_root else Path(__file__).resolve().parent.parent
    rubric = load_rubric(plugin_root)

    scores = read_scores(vault)
    gaps = identify_gaps(scores, rubric)
    s_total = scores.get("structural", {}).get("total", 0)
    c_total = scores.get("content", {}).get("total", 0) if scores.get("content") else 0
    combined = s_total + c_total

    print(json.dumps({
        "scores": {
            "structural": s_total,
            "content": c_total,
            "combined": combined,
        },
        "gaps": gaps[:10],  # top 10 worst gaps
        "stop_check": stop_check(scores, rubric),
        "watchdog_triggered": delta_watchdog(
            vault, combined,
            rubric["safety"]["delta_watchdog"]["consecutive_rounds"],
            rubric["safety"]["delta_watchdog"]["min_delta"]
        ),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
