"""Cost + token + concurrency caps for the auto-pilot headless driver.

Self-contained budget helpers extracted from ``headless-loop.py`` so they can
be unit-tested in isolation and reused by other entry points (e.g. a PM-side
mid-iter check). The module surfaces three pure-ish callables:

- :func:`parse_session_usage` — best-effort scan of a claude session log for
  the latest cost + token totals. Defensive: scans per-line so a stray
  ``cost``-or-``tokens`` keyword does not pair with a number on an unrelated
  line. Falls back to ``(0.0, 0)`` when the log has nothing parseable, and
  the caller substitutes a per-iter estimate.
- :func:`count_claude_pids` — fork-bomb signal via ``pgrep -x claude``.
  Returns 0 when ``pgrep`` is absent so missing tools degrade to "no signal"
  rather than "fork-bomb in progress".
- :func:`check_caps` — single entry point used by the loop driver to decide
  whether to terminate the run with status ``"cost-cap"``.

These functions are deliberately read-only with respect to ``state.json``;
the driver owns persisting any accumulated counters.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

from _log import event
from _state import State

# Per-line patterns. ``[^\d\n]*`` bounds the lookahead so the keyword and the
# captured number must sit on the same line — guards against false positives
# like ``"cost was free.\n999 errors"``. The keyword side stays permissive so
# both ``total cost: $0.42`` and ``cost = 0.42`` parse.
_COST_LINE = re.compile(
    r"(?:total\s+cost|cost)[^\d\n]*?\$?\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_TOKEN_LINE = re.compile(
    r"(?:total\s+tokens?|tokens?\s+used)[^\d\n]*?(\d+)",
    re.IGNORECASE,
)


def parse_session_usage(log_path: Path) -> tuple[float, int]:
    """Return ``(cost_usd, tokens)`` parsed from a claude session log.

    Scans line-by-line; takes the maximum across all matches per metric so a
    later "Total cost" line wins over an earlier interim cost. Returns
    ``(0.0, 0)`` when the log is absent or carries no recognizable totals.

    Args:
        log_path: per-iter session log written by the driver.
    """
    if not log_path.exists():
        return 0.0, 0
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return 0.0, 0
    cost = 0.0
    tokens = 0
    for line in text.splitlines():
        m_cost = _COST_LINE.search(line)
        if m_cost is not None:
            try:
                cost = max(cost, float(m_cost.group(1)))
            except ValueError:
                pass
        m_tok = _TOKEN_LINE.search(line)
        if m_tok is not None:
            try:
                tokens = max(tokens, int(m_tok.group(1)))
            except ValueError:
                pass
    return cost, tokens


def count_claude_pids() -> int:
    """Return the count of running ``claude`` processes via ``pgrep -x claude``.

    Treats a missing ``pgrep`` as a zero signal — better to under-detect than
    refuse to spawn on every host where the tool is unavailable.
    """
    if shutil.which("pgrep") is None:
        return 0
    try:
        res = subprocess.run(
            ["pgrep", "-x", "claude"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0
    if res.returncode == 0:
        return len([line for line in res.stdout.splitlines() if line.strip()])
    return 0


def check_caps(args: argparse.Namespace, state: State) -> str | None:
    """Return ``"cost-cap"`` when any budget cap is exceeded, else ``None``.

    Checks (in order):
      - accumulated USD vs ``--max-cost-usd``
      - accumulated tokens vs ``--max-tokens``
      - live ``claude`` pid count vs ``--max-concurrent-claude``
    """
    cost = float(state.get("cost_usd", 0.0))
    tokens = int(state.get("tokens", 0))
    if cost > args.max_cost_usd:
        event("cap.cost_exceeded", cost_usd=cost, cap=args.max_cost_usd)
        return "cost-cap"
    if tokens > args.max_tokens:
        event("cap.tokens_exceeded", tokens=tokens, cap=args.max_tokens)
        return "cost-cap"
    pids = count_claude_pids()
    if pids >= args.max_concurrent_claude:
        event("cap.pid_count_exceeded", pids=pids, cap=args.max_concurrent_claude)
        return "cost-cap"
    return None
