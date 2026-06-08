#!/usr/bin/env python3
"""PM driver for source-migration.

Issues one ticket per (src_notebook → dst_notebook). Workers poll, claim,
execute notebooklm CLI, deliver. PM verifies source count delta.

CLI:
    pm.py issue --category ai-libraries --dst <notebook-id> [--limit N]
    pm.py status
    pm.py verify-all
    pm.py reset  # clears tickets (DANGEROUS)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import TextIO

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ticket_system import TicketBoard, TicketStatus  # noqa: E402

PLUGIN_ROOT_P = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_ROOT_P))
from sources.notebooklm import _classify_title  # noqa: E402

BOARD_PATH = Path.home() / ".vault-builder" / "migrate-tickets.json"


def _write_line(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")


def _emit(message: str) -> None:
    _write_line(sys.stdout, message)


def _warn(message: str) -> None:
    _write_line(sys.stderr, message)


def _list_notebooks() -> list[dict]:
    r = subprocess.run(["notebooklm", "list", "--json"], capture_output=True, text=True, timeout=30)
    return json.loads(r.stdout).get("notebooks", [])


def _source_count(nid: str) -> int:
    r = subprocess.run(["notebooklm", "source", "list", "-n", nid, "--json"],
                       capture_output=True, text=True, timeout=30)
    try:
        return len(json.loads(r.stdout).get("sources", []))
    except Exception as exc:
        _warn(f"migrate/pm: _source_count JSON parse failed for {nid}: {type(exc).__name__}: {exc}")
        return -1


def cmd_issue(args) -> int:
    board = TicketBoard(BOARD_PATH)
    nbs = _list_notebooks()
    targets = [nb for nb in nbs if _classify_title(nb["title"]) == args.category and nb["id"] != args.dst]
    if args.limit:
        targets = targets[: args.limit]

    dst_baseline = _source_count(args.dst)
    _emit(f"dst notebook source baseline: {dst_baseline}")

    issued = 0
    for nb in targets:
        src_n = _source_count(nb["id"])
        if src_n <= 0:
            continue
        contract = {
            "goal": f"Add {src_n} sources from '{nb['title']}' into dst notebook with title prefix.",
            "src_id": nb["id"],
            "src_title": nb["title"],
            "dst_id": args.dst,
            "title_prefix": f"[{nb['title']}]",
            "expected_added": src_n,
            "acceptance": f"dst source count increases by {src_n}",
        }
        t = board.issue(round_num=1, worker_type="source-migrator", contract=contract)
        _emit(f"  + {t.id}  src={nb['title'][:50]} ({src_n} sources)")
        issued += 1
    _emit(f"\nIssued {issued} tickets → {BOARD_PATH}")
    return 0


def cmd_status(args) -> int:
    board = TicketBoard(BOARD_PATH)
    summary = board.round_summary(1)
    _emit(json.dumps(summary, ensure_ascii=False, indent=2))
    for tid, t in board.tickets.items():
        flag = {"verified": "✓", "rejected": "✗", "delivered": "⊙", "in_progress": "▶", "pending": "·"}.get(
            t.status.value, "?")
        _emit(f"  {flag} {tid}  retry={t.retry_count}  {t.contract.get('src_title','')[:50]}")
    return 0


def cmd_verify(args) -> int:
    """Verify all delivered tickets — check dst source count vs expected."""
    board = TicketBoard(BOARD_PATH)
    delivered = [t for t in board.tickets.values() if t.status == TicketStatus.DELIVERED]
    if not delivered:
        _emit("No delivered tickets to verify.")
        return 0

    dst_id = delivered[0].contract["dst_id"]
    dst_now = _source_count(dst_id)

    def verifier(t):
        added_ids = t.verification.get("added_ids") if t.verification else None
        if not added_ids and t.deliverable_paths:
            added_ids = t.deliverable_paths
        expected = t.contract["expected_added"]
        got = len(added_ids or [])
        if got >= expected:
            return True, f"added {got}/{expected}", float(got)
        return False, f"only added {got}/{expected}; redo missing sources", 0.0

    for t in delivered:
        ok = board.verify(t.id, verifier)
        mark = "✓" if ok else "✗"
        _emit(f"  {mark} {t.id}  {t.verification.get('feedback','')}")

    _emit(f"\ndst source count now: {dst_now}")
    return 0


def cmd_reissue(args) -> int:
    """Reset rejected tickets to pending so workers re-process (idempotent)."""
    board = TicketBoard(BOARD_PATH)
    rejected = [t for t in board.tickets.values() if t.status == TicketStatus.REJECTED]
    if not rejected:
        _emit("No rejected tickets.")
        return 0
    for t in rejected:
        try:
            board.reissue(t.id, additional_feedback="Idempotent worker will skip already-migrated; retry missing.")
            _emit(f"  ↺ {t.id}  retry={t.retry_count}")
        except RuntimeError as e:
            _emit(f"  ! {t.id}  {e}")
    return 0


def cmd_reset(args) -> int:
    if BOARD_PATH.exists():
        BOARD_PATH.unlink()
        _emit(f"Removed {BOARD_PATH}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    issue = sub.add_parser("issue")
    issue.add_argument("--category", required=True)
    issue.add_argument("--dst", required=True, help="Target notebook ID")
    issue.add_argument("--limit", type=int, default=0)
    issue.set_defaults(func=cmd_issue)

    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("verify").set_defaults(func=cmd_verify)
    sub.add_parser("reissue").set_defaults(func=cmd_reissue)
    sub.add_parser("reset").set_defaults(func=cmd_reset)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
