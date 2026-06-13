"""Cost + token + concurrency caps for the auto-pilot headless driver.

Self-contained budget helpers extracted from ``headless-loop.py`` so they can
be unit-tested in isolation and reused by other entry points (e.g. a PM-side
mid-iter check). The module surfaces five pure-ish callables:

- :func:`parse_result_json` — structured-first scan of ``claude -p`` output
  for a ``{"type":"result"}`` JSON line; returns ``(cost_usd, tokens)`` or
  ``None`` when no such line exists.
- :func:`parse_session_usage` — best-effort scan of a claude session log for
  the latest cost + token totals. Tries structured JSON first; falls back to
  regex. Defensive: scans per-line so a stray ``cost``-or-``tokens`` keyword
  does not pair with a number on an unrelated line. Falls back to ``(0.0, 0)``
  when the log has nothing parseable, and the caller substitutes a per-iter
  estimate.
- :func:`append_usage_ledger` — append one JSONL record to the per-run usage
  ledger; advisory (OSError is swallowed, never crashes the loop).
- :func:`count_claude_pids` — fork-bomb signal via ``pgrep -x claude``.
  Returns 0 when ``pgrep`` is absent so missing tools degrade to "no signal"
  rather than "fork-bomb in progress".
- :func:`check_caps` — single entry point used by the loop driver to decide
  whether to terminate the run with status ``"cost-cap"``.
- :func:`check_wall_clock` — pure deadline check; returns ``"time-cap"`` when
  the monotonic deadline has passed, else ``None``.

These functions are deliberately read-only with respect to ``state.json``;
the driver owns persisting any accumulated counters.
"""
from __future__ import annotations

import argparse
import json
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


def parse_result_json(text: str) -> tuple[float, int] | None:
    """Scan *text* for a ``{"type":"result"}`` JSON line emitted by ``claude -p``.

    Returns ``(cost_usd, tokens)`` from the LAST such line found, or ``None``
    when no parseable result line exists. Malformed JSON lines are silently
    skipped. Token count is the sum of all integer values in the ``usage``
    sub-dict whose key ends with ``_tokens``; boolean values are excluded.

    Args:
        text: raw stdout/stderr text from a claude session log.
    """
    result: tuple[float, int] | None = None
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(obj, dict) or obj.get("type") != "result":
            continue
        cost = 0.0
        raw_cost = obj.get("total_cost_usd")
        if raw_cost is not None:
            try:
                cost = float(raw_cost)
            except (TypeError, ValueError):
                pass
        tokens = 0
        usage = obj.get("usage", {})
        if isinstance(usage, dict):
            for k, v in usage.items():
                if k.endswith("_tokens") and isinstance(v, int) and not isinstance(v, bool):
                    tokens += v
        result = (cost, tokens)
    return result


def parse_session_usage(log_path: Path) -> tuple[float, int]:
    """Return ``(cost_usd, tokens)`` parsed from a claude session log.

    Tries structured JSON first (``parse_result_json``); falls through to the
    per-line regex scan when no result line is found. Takes the maximum across
    all regex matches per metric so a later "Total cost" line wins over an
    earlier interim cost. Returns ``(0.0, 0)`` when the log is absent or
    carries no recognizable totals.

    Args:
        log_path: per-iter session log written by the driver.
    """
    if not log_path.exists():
        return 0.0, 0
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return 0.0, 0
    structured = parse_result_json(text)
    if structured is not None:
        return structured
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


def append_usage_ledger(ledger_path: Path, record: dict[str, object]) -> None:
    """Append one JSONL record to the per-run usage ledger; advisory, never raises.

    OSError is caught and logged via ``event``; ledger write failures do not
    affect loop status or cost accounting in state.json.

    Args:
        ledger_path: path to the JSONL ledger file (created if absent).
        record: dict containing iter, phase, cost_usd, tokens, etc.
    """
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ledger_path, "a") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as exc:
        event("ledger.write_failed", error_type=type(exc).__name__)


def check_wall_clock(deadline_monotonic: float | None, now_monotonic: float) -> str | None:
    """Return ``"time-cap"`` when the wall-clock deadline has passed, else ``None``.

    Pure — caller injects the current monotonic time so this can be tested
    without patching ``time.monotonic``. Does NOT fold into ``check_caps``
    (that function is state-driven + clock-free; wall-clock is separate).

    Args:
        deadline_monotonic: ``time.monotonic()`` value at which the run must
            stop. ``None`` means the watchdog is disabled.
        now_monotonic: current ``time.monotonic()`` value.
    """
    if deadline_monotonic is not None and now_monotonic >= deadline_monotonic:
        return "time-cap"
    return None


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
      - ``claude`` pid GROWTH over ``args.pid_baseline`` vs
        ``--max-concurrent-claude``. The baseline (pid count at driver start,
        captured by ``headless-loop.main``) keeps unrelated sessions on a busy
        host from tripping the fork-bomb signal; absent attribute = baseline 0,
        which preserves the old absolute-count behavior.
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
    baseline = int(getattr(args, "pid_baseline", 0))
    if pids - baseline >= args.max_concurrent_claude:
        event("cap.pid_count_exceeded", pids=pids, baseline=baseline,
              cap=args.max_concurrent_claude)
        return "cost-cap"
    return None
