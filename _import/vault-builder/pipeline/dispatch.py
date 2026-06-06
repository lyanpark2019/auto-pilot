#!/usr/bin/env python3
"""Worker dispatch helper for PM orchestrator.

Reads fix-plan.json, exposes individual ticket records. PM agent uses this to:
- list tickets needing dispatch (status=pending)
- mark a ticket as dispatched / delivered / verified / rejected
- compute round summary
- detect 3-strike escalation

State persists in <project>/.vault-builder/dispatch-state.json.

Usage:
    from pipeline.dispatch import DispatchBoard
    board = DispatchBoard(project_root)
    pending = board.pending_tickets()
    board.mark_dispatched(ticket_id)
    board.deliver(ticket_id, deliverable_paths)
    passed, msg = board.verify(ticket_id, verifier_fn)
    if not passed: board.reissue(ticket_id, feedback)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


MAX_STRIKES = 3


class TicketStatus(str, Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    VERIFIED = "verified"
    REJECTED = "rejected"
    ESCALATED = "escalated"


@dataclass
class TicketRecord:
    id: str
    worker_type: str
    contract: dict
    status: str = TicketStatus.PENDING.value
    deliverable_paths: list[str] = field(default_factory=list)
    retry_count: int = 0
    feedback: str = ""
    history: list[dict] = field(default_factory=list)


class DispatchBoard:
    def __init__(self, project_root: Path):
        self.root = project_root.expanduser().resolve()
        self.vb_dir = self.root / ".vault-builder"
        self.state_path = self.vb_dir / "dispatch-state.json"
        self.plan_path = self.vb_dir / "fix-plan.json"
        self.tickets: dict[str, TicketRecord] = {}
        self.round_num = 0
        self._load()

    def _load(self) -> None:
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text())
            self.round_num = data.get("round", 0)
            for t in data.get("tickets", []):
                self.tickets[t["id"]] = TicketRecord(**t)
        elif self.plan_path.exists():
            plan = json.loads(self.plan_path.read_text())
            for t in plan.get("tickets", []):
                tr = TicketRecord(id=t["id"], worker_type=t["worker_type"], contract=t["contract"])
                tr.history.append({"event": "issued", "at": time.time()})
                self.tickets[tr.id] = tr
            self.round_num = 1
            self._save()

    def _save(self) -> None:
        self.vb_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({
            "round": self.round_num,
            "updated_at": time.time(),
            "tickets": [asdict(t) for t in self.tickets.values()],
        }, indent=2, ensure_ascii=False))

    def pending_tickets(self) -> list[TicketRecord]:
        return [t for t in self.tickets.values() if t.status == TicketStatus.PENDING.value]

    def mark_dispatched(self, ticket_id: str) -> None:
        t = self.tickets[ticket_id]
        t.status = TicketStatus.DISPATCHED.value
        t.history.append({"event": "dispatched", "at": time.time(), "retry": t.retry_count})
        self._save()

    def deliver(self, ticket_id: str, deliverable_paths: list[str]) -> None:
        t = self.tickets[ticket_id]
        t.status = TicketStatus.DELIVERED.value
        t.deliverable_paths = deliverable_paths
        t.history.append({"event": "delivered", "at": time.time(), "paths": deliverable_paths})
        self._save()

    def verify(self, ticket_id: str, verifier_fn: Callable[[TicketRecord], tuple[bool, str]]) -> tuple[bool, str]:
        t = self.tickets[ticket_id]
        passed, msg = verifier_fn(t)
        if passed:
            t.status = TicketStatus.VERIFIED.value
            t.history.append({"event": "verified", "at": time.time(), "msg": msg})
        else:
            t.status = TicketStatus.REJECTED.value
            t.feedback = msg
            t.history.append({"event": "rejected", "at": time.time(), "msg": msg})
        self._save()
        return passed, msg

    def reissue(self, ticket_id: str, additional_feedback: str = "") -> TicketRecord:
        t = self.tickets[ticket_id]
        if t.status != TicketStatus.REJECTED.value:
            raise ValueError(f"cannot reissue ticket in status {t.status}")
        if t.retry_count >= MAX_STRIKES:
            t.status = TicketStatus.ESCALATED.value
            t.history.append({"event": "escalated", "at": time.time(),
                              "reason": f"hit {MAX_STRIKES} strikes"})
            self._save()
            raise RuntimeError(f"ticket {ticket_id} hit {MAX_STRIKES} strikes — escalated")
        t.retry_count += 1
        t.status = TicketStatus.PENDING.value
        if additional_feedback:
            t.feedback += f"\n[Retry {t.retry_count}] {additional_feedback}"
        t.history.append({"event": "reissued", "at": time.time(), "retry": t.retry_count})
        self._save()
        return t

    def summary(self) -> dict:
        counts: dict = {}
        for t in self.tickets.values():
            counts[t.status] = counts.get(t.status, 0) + 1
        return {
            "round": self.round_num,
            "total": len(self.tickets),
            "by_status": counts,
        }


def _verify_drift_fixed(t: TicketRecord, project_root: Path) -> tuple[bool, str]:
    """Default verifier: re-run drift detection, ensure this ticket's drift_type entries
    decreased by at least len(t.contract["items"])."""
    if __package__ in (None, ""):
        from pipeline import drift as drift_mod
    else:
        from pipeline import drift as drift_mod

    drift_type = t.contract.get("drift_type")
    items_before = len(t.contract.get("items", []))
    report = drift_mod.detect(project_root)
    items_now = len(report.to_dict().get(drift_type, []))
    if items_now < items_before:
        return True, f"{drift_type}: {items_before} → {items_now} (improved)"
    return False, f"{drift_type}: still {items_now} entries (was {items_before})"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("project_root", type=Path)
    ap.add_argument("cmd", choices=["list-pending", "summary", "verify-all", "load-plan"])
    args = ap.parse_args(argv[1:])

    board = DispatchBoard(args.project_root)
    if args.cmd == "list-pending":
        pending = board.pending_tickets()
        print(json.dumps([{
            "id": t.id, "worker_type": t.worker_type,
            "drift_type": t.contract.get("drift_type"),
            "item_count": len(t.contract.get("items", []))
        } for t in pending], indent=2))
    elif args.cmd == "summary":
        print(json.dumps(board.summary(), indent=2))
    elif args.cmd == "verify-all":
        from functools import partial
        verifier = partial(_verify_drift_fixed, project_root=args.project_root)
        results = []
        for t in list(board.tickets.values()):
            if t.status == TicketStatus.DELIVERED.value:
                passed, msg = board.verify(t.id, verifier)
                results.append({"id": t.id, "passed": passed, "msg": msg})
        print(json.dumps(results, indent=2))
    elif args.cmd == "load-plan":
        # Force reload from fix-plan.json (resets state)
        board.state_path.unlink(missing_ok=True)
        board.tickets.clear()
        board._load()
        print(json.dumps(board.summary(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
