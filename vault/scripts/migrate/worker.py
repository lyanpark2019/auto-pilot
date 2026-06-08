#!/usr/bin/env python3
"""Worker that polls migrate-tickets, claims one, executes notebooklm source add.

Atomic claim via TicketBoard.start() + status flip. Mechanical work: no LLM.

Loop:
    1. Find PENDING ticket
    2. board.start() to flip to IN_PROGRESS
    3. List src sources → for each: add to dst with prefixed title
    4. board.deliver(added_ids)
    5. Sleep + repeat

Exit:
    --once   stop after first ticket
    --max N  stop after N tickets
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from ticket_system import TicketBoard, TicketStatus  # noqa: E402

BOARD_PATH = Path.home() / ".vault-builder" / "migrate-tickets.json"
WORKER_ID = f"w-{os.getpid()}"


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    sys.stdout.write(f"[{ts}] {WORKER_ID}  {msg}\n")
    sys.stdout.flush()


def _list_sources(nid: str) -> list[dict]:
    r = subprocess.run(["notebooklm", "source", "list", "-n", nid, "--json"],
                       capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout).get("sources", [])


def _existing_titles(dst: str) -> set[str]:
    """Titles already in dst — for idempotent skip."""
    try:
        return {s.get("title", "") for s in _list_sources(dst)}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, AttributeError, TypeError) as exc:
        log(f"  ! _existing_titles failed for {dst}: {exc}")
        return set()


def _effective_url(source: dict) -> str | None:
    stype = str(source.get("type", "")).split(".")[-1].lower()
    url = source.get("url")
    raw_title = source.get("title", "")
    if stype in ("youtube", "url") and isinstance(url, str) and url:
        return url
    if isinstance(raw_title, str) and raw_title.startswith(("http://", "https://")):
        return raw_title
    return None


def _source_fulltext(source: dict) -> str:
    full = subprocess.run(
        ["notebooklm", "source", "fulltext", source["id"], "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        return json.loads(full.stdout).get("content", "")
    except (json.JSONDecodeError, AttributeError) as exc:
        log(f"  ! fulltext JSON parse failed for source {source.get('id','?')}: {exc}")
        return ""


def _parse_added_source_id(stdout: str, title: str) -> str | None:
    try:
        data = json.loads(stdout)
        return data.get("id") or data.get("source", {}).get("id")
    except (json.JSONDecodeError, AttributeError) as exc:
        log(f"  ! add-source JSON parse failed for {title[:60]}: {exc}")
        return None


def _add_source(dst: str, source: dict, prefix: str) -> str | None:
    """Add one source to dst notebook with title prefix."""
    title = f"{prefix} {source.get('title','')}".strip()
    base = ["notebooklm", "source", "add", "-n", dst, "--title", title, "--json"]
    effective_url = _effective_url(source)
    if effective_url:
        cmd = base + ["--", effective_url]
    else:
        text = _source_fulltext(source)
        if not text:
            log(f"  ! skip (no content, no url): {title[:60]}")
            return None
        cmd = base + ["--type", "text", "--", text]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        log(f"  ! add failed: {r.stderr[:200]}")
        return None
    return _parse_added_source_id(r.stdout, title)


LOCK_PATH = Path.home() / ".vault-builder" / "migrate-tickets.lock"


def _claim_next(board: TicketBoard):
    """Pick a pending ticket atomically. fcntl exclusive lock prevents worker races."""
    import fcntl

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_PATH, "w") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            board.load()
            for tid, t in board.tickets.items():
                if t.status == TicketStatus.PENDING:
                    board.start(tid)  # writes status=IN_PROGRESS to disk
                    return board.tickets[tid]
            return None
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def process(t) -> bool:
    log(f"START {t.id}  src='{t.contract['src_title'][:50]}'")
    sources = _list_sources(t.contract["src_id"])
    log(f"  {len(sources)} sources to migrate")
    existing = _existing_titles(t.contract["dst_id"])
    added = []
    skipped = 0
    for s in sources:
        title = f"{t.contract['title_prefix']} {s.get('title','')}".strip()
        if title in existing:
            skipped += 1
            added.append(f"skip:{s['id'][:8]}")
            log(f"  = (skip-existing) {title[:70]}")
            continue
        sid = _add_source(t.contract["dst_id"], s, t.contract["title_prefix"])
        if sid:
            added.append(sid)
            log(f"  + {sid[:8]}  {s.get('title','')[:60]}")
        time.sleep(0.5)  # gentle rate-limit
    board = TicketBoard(BOARD_PATH)
    board.deliver(t.id, added)
    # Stash added_ids in verification for PM verify
    board.tickets[t.id].verification = {"added_ids": added, "skipped": skipped}
    board.save()
    log(f"DELIVER {t.id}  added={len(added)}/{len(sources)} (skipped={skipped})")
    return len(added) == len(sources)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--poll-interval", type=float, default=3.0)
    args = ap.parse_args()

    if not BOARD_PATH.exists():
        log(f"No board at {BOARD_PATH}. Issue tickets first.")
        return 1

    log(f"Worker started. Board: {BOARD_PATH}")
    processed = 0
    while True:
        board = TicketBoard(BOARD_PATH)
        t = _claim_next(board)
        if t is None:
            log("No pending tickets — idle.")
            if args.once or args.max:
                break
            time.sleep(args.poll_interval)
            continue
        process(t)
        processed += 1
        if args.once or (args.max and processed >= args.max):
            break
    log(f"Worker exit. Processed {processed} tickets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
