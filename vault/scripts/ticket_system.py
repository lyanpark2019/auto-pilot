#!/usr/bin/env python3
"""
Ticket/Contract system for PM-Worker orchestration.

티켓 발행 → worker dispatch → deliverable 검증 → reward or rejection-with-feedback → retry.

Usage:
    from ticket_system import TicketBoard, Ticket
    board = TicketBoard(state_path)
    t = board.issue(worker='vault-structure-curator', contract={...})
    # dispatch worker with t.to_prompt_context()
    board.deliver(t.id, outputs_paths)
    verified = board.verify(t.id, verifier_fn)
    if not verified: board.reissue(t.id, feedback='...')
"""

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, Callable, Any


class TicketStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass
class Ticket:
    id: str
    round_num: int
    worker_type: str
    contract: dict
    status: TicketStatus = TicketStatus.PENDING
    deliverable_paths: list = field(default_factory=list)
    verification: dict = field(default_factory=dict)
    reward: float = 0.0
    feedback: str = ""
    retry_count: int = 0
    created_at: float = field(default_factory=time.time)
    delivered_at: Optional[float] = None
    verified_at: Optional[float] = None
    history: list = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Generate prompt block to inject into worker dispatch."""
        ctx = [
            f"# Ticket {self.id} (round {self.round_num})",
            f"**Worker type**: {self.worker_type}",
            f"**Retry**: {self.retry_count}",
            "",
            f"## Contract",
            f"**Goal**: {self.contract.get('goal','')}",
            f"**Acceptance criteria**: {self.contract.get('acceptance','')}",
            f"**Inputs**: {', '.join(self.contract.get('inputs', []))}",
            f"**Outputs required**: {', '.join(self.contract.get('outputs', []))}",
            f"**Reward on verify**: {self.contract.get('reward', 0)} pts",
        ]
        if self.feedback and self.retry_count > 0:
            ctx += [
                "",
                f"## Previous attempt feedback (FIX THESE)",
                self.feedback,
            ]
        return "\n".join(ctx)


class TicketBoard:
    """Persistent ticket board with state on disk."""

    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self.tickets: dict[str, Ticket] = {}
        self.load()

    def load(self):
        if self.state_path.exists():
            data = json.loads(self.state_path.read_text())
            for tid, t in data.get("tickets", {}).items():
                t["status"] = TicketStatus(t["status"])
                self.tickets[tid] = Ticket(**t)

    def save(self):
        data = {
            "tickets": {
                tid: {**asdict(t), "status": t.status.value}
                for tid, t in self.tickets.items()
            },
            "updated_at": time.time(),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def issue(self, round_num: int, worker_type: str, contract: dict) -> Ticket:
        """PM issues new ticket."""
        tid = f"T-R{round_num}-{worker_type[:6]}-{uuid.uuid4().hex[:4]}"
        t = Ticket(id=tid, round_num=round_num, worker_type=worker_type, contract=contract)
        t.history.append({"event": "issued", "at": time.time()})
        self.tickets[tid] = t
        self.save()
        return t

    def start(self, ticket_id: str):
        t = self.tickets[ticket_id]
        t.status = TicketStatus.IN_PROGRESS
        t.history.append({"event": "started", "at": time.time()})
        self.save()

    def deliver(self, ticket_id: str, deliverable_paths: list):
        """Worker reports completion."""
        t = self.tickets[ticket_id]
        t.status = TicketStatus.DELIVERED
        t.deliverable_paths = deliverable_paths
        t.delivered_at = time.time()
        t.history.append({"event": "delivered", "at": t.delivered_at, "paths": deliverable_paths})
        self.save()

    def verify(self, ticket_id: str, verifier_fn: Callable[[Ticket], tuple[bool, str, float]]) -> bool:
        """PM verifies deliverable. verifier_fn returns (passed, feedback, reward_credit)."""
        t = self.tickets[ticket_id]
        passed, feedback, reward = verifier_fn(t)
        t.verification = {"passed": passed, "feedback": feedback, "reward_credit": reward, "at": time.time()}
        if passed:
            t.status = TicketStatus.VERIFIED
            t.reward = reward
            t.verified_at = time.time()
            t.history.append({"event": "verified", "reward": reward, "at": time.time()})
        else:
            t.status = TicketStatus.REJECTED
            t.feedback = feedback
            t.history.append({"event": "rejected", "feedback": feedback, "at": time.time()})
        self.save()
        return passed

    def reissue(self, ticket_id: str, additional_feedback: str = "", retry_cap: int = 3) -> Ticket:
        """Retry rejected ticket with feedback. 3-strike escalation per safety rubric."""
        t = self.tickets[ticket_id]
        if t.status != TicketStatus.REJECTED:
            raise ValueError(f"Cannot reissue ticket in status {t.status}")
        if t.retry_count >= retry_cap:
            t.history.append({"event": "escalated", "retry": t.retry_count, "at": time.time(),
                              "reason": f"hit retry_cap={retry_cap} — needs user escalation"})
            self.save()
            raise RuntimeError(f"Ticket {ticket_id} hit retry cap {retry_cap}. Escalate to user.")
        t.status = TicketStatus.PENDING
        t.retry_count += 1
        if additional_feedback:
            t.feedback += f"\n\n[Retry {t.retry_count}] {additional_feedback}"
        t.history.append({"event": "reissued", "retry": t.retry_count, "at": time.time()})
        self.save()
        return t

    def round_summary(self, round_num: int) -> dict:
        """Stats for a round."""
        round_tickets = [t for t in self.tickets.values() if t.round_num == round_num]
        return {
            "round": round_num,
            "total": len(round_tickets),
            "by_status": {s.value: sum(1 for t in round_tickets if t.status == s) for s in TicketStatus},
            "total_reward": sum(t.reward for t in round_tickets if t.status == TicketStatus.VERIFIED),
            "avg_retries": sum(t.retry_count for t in round_tickets) / max(len(round_tickets), 1),
        }

    def all_verified(self, round_num: int) -> bool:
        round_tickets = [t for t in self.tickets.values() if t.round_num == round_num]
        return all(t.status == TicketStatus.VERIFIED for t in round_tickets)


if __name__ == "__main__":
    # Demo
    import sys
    board = TicketBoard(Path("/tmp/ticket-demo.json"))
    t = board.issue(round_num=1, worker_type="vault-structure-curator", contract={
        "goal": "Label 41 communities with real 2-5 word names",
        "inputs": ["graph.json", ".graphify_analysis.json"],
        "outputs": [".graphify_labels.json per cat"],
        "acceptance": "0 placeholders across 7 cats",
        "reward": 15,
    })
    print(t.to_prompt_context())
    print("\nSummary:", board.round_summary(1))
