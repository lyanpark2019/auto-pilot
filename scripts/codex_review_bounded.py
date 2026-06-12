#!/usr/bin/env python3
"""Bounded codex reviewer invocation: risk-tiered effort, portable timeout,
one retry at lower effort, honest ABSTAIN on exhaustion.

Invoked by agents/auto-pilot-codex-reviewer.md instead of a bare `codex exec`.
Codex is a second opinion — its unavailability never blocks the round
(model-routing.md): on double timeout/failure this wrapper writes a
schema-valid review.json with verdict=ABSTAIN + reviewer_meta.abstain_reason
so the evidence gate (scripts/_evidence.py) can tell an honest abstain from a
silent skip.

Sandbox note: hooks/pre-reviewer-write.sh greps Bash commands for a bare
`codex` token to require --sandbox read-only; the python indirection hides the
inner call from that grep, so build_argv() HARDCODES the flag and a unit test
pins it. Timeout uses subprocess.run(timeout=) — portable, no gtimeout dep.

Exit codes: 0 codex completed (raw stdout saved; caller writes review.json),
3 ABSTAIN review.json written, 2 usage/ticket error.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _heartbeat
import _routing
import _subagent_helpers

ABSTAIN_EXIT = 3
_TIMEOUT_RC = 124


def build_argv(effort: str) -> list[str]:
    """Real codex argv. --sandbox read-only is non-negotiable (see module doc)."""
    return [
        "codex", "exec", "--sandbox", "read-only", "--json",
        "-c", f"model_reasoning_effort={effort}",
        "--prompt-file", "-",
    ]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _attempt(
    argv: list[str], prompt: str, raw_path: Path, timeout_s: int
) -> tuple[int, str]:
    """Run one codex attempt; returns (0, "") on success, else (rc, reason)."""
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            argv,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _TIMEOUT_RC, "codex-timeout"
    except FileNotFoundError:
        return 127, "codex-exec-failed"
    raw_path.write_text(proc.stdout)
    if proc.returncode != 0:
        return proc.returncode, "codex-exec-failed"
    return 0, ""


def _abstain_review(
    contract_id: str,
    argv: list[str],
    tier: str,
    effort: str,
    reason: str,
    started_at: str,
    rc: int = _TIMEOUT_RC,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "reviewer": "codex-reviewer",
        "contract_id": contract_id,
        "verdict": "ABSTAIN",
        "scope_check": "SKIPPED",
        "findings": [],
        "verify_rerun": {"cmd": shlex.join(argv), "exit_code": rc},
        "reviewer_meta": {
            "model": "codex",
            "codex_invocation": shlex.join(argv),
            "started_at": started_at,
            "ended_at": _now_iso(),
            "abstain_reason": reason,
            "risk_tier": tier,
            "effort": effort,
        },
    }


def run(
    ticket_path: Path,
    tier: str,
    prompt_file: Path,
    config: Path | None,
    codex_cmd: str | None,
) -> int:
    """Drive attempt -> retry(lower effort) -> ABSTAIN. See module docstring."""
    try:
        ticket = json.loads(ticket_path.read_text())
        out_dir = Path(str(ticket["output_dir"]))
        contract_id = str(ticket["contract_id"])
        prompt = prompt_file.read_text()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"codex_review_bounded: bad ticket/prompt: {exc}\n")
        return 2

    started_at = _now_iso()
    try:
        efforts = [_routing.effort_for_tier(tier, config=config)]
        efforts.append(_routing.lower_effort(efforts[0]))
        timeouts = list(_routing.codex_timeouts(config=config))
    except _routing.RoutingConfigError as exc:
        sys.stderr.write(f"codex_review_bounded: bad routing config: {exc}\n")
        return 2

    reason = ""
    rc = _TIMEOUT_RC
    for attempt, (effort, timeout_s) in enumerate(zip(efforts, timeouts), start=1):
        argv = shlex.split(codex_cmd) if codex_cmd else build_argv(effort)
        _heartbeat.write_beat(
            out_dir, "codex-reviewer", f"codex-attempt-{attempt}:{effort}",
            risk_tier=tier,
        )
        raw = out_dir / f"codex-raw-attempt-{attempt}.json"
        rc, reason = _attempt(argv, prompt, raw, timeout_s)
        if rc == 0:
            _heartbeat.write_beat(
                out_dir, "codex-reviewer", f"codex-done:{effort}",
                risk_tier=tier,
            )
            return 0

    final_argv = shlex.split(codex_cmd) if codex_cmd else build_argv(efforts[-1])
    review = _abstain_review(contract_id, final_argv, tier, efforts[-1], reason, started_at, rc=rc)
    _subagent_helpers.atomic_write_output(out_dir, "review.json", review)
    _heartbeat.write_beat(
        out_dir, "codex-reviewer", f"abstained:{reason}", risk_tier=tier
    )
    return ABSTAIN_EXIT


def main(argv: list[str] | None = None) -> int:
    """CLI entry point — see module docstring for the exit-code contract."""
    parser = argparse.ArgumentParser(prog="codex_review_bounded")
    parser.add_argument("--ticket", required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--config", default=None,
                        help="alternate model-routing.yaml (tests)")
    parser.add_argument("--codex-cmd", default=None,
                        help="TEST-ONLY full argv override (shlex string)")
    args = parser.parse_args(argv)
    return run(
        Path(args.ticket),
        args.tier,
        Path(args.prompt_file),
        Path(args.config) if args.config else None,
        args.codex_cmd,
    )


if __name__ == "__main__":
    raise SystemExit(main())
