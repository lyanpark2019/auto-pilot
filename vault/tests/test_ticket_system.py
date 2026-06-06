"""Tests for ticket_system: issue/deliver/verify/reissue/3-strike."""
from __future__ import annotations

from pathlib import Path

import pytest

from ticket_system import TicketBoard, TicketStatus


def _board(tmp_path: Path) -> TicketBoard:
    return TicketBoard(tmp_path / "ticket-state.json")


def test_issue_creates_pending_ticket(tmp_path: Path) -> None:
    board = _board(tmp_path)
    t = board.issue(round_num=1, worker_type="community-labeler", contract={"goal": "G", "reward": 10})
    assert t.status == TicketStatus.PENDING
    assert t.round_num == 1
    assert t.id in board.tickets
    assert (tmp_path / "ticket-state.json").exists()


def test_deliver_then_verify_pass(tmp_path: Path) -> None:
    board = _board(tmp_path)
    t = board.issue(round_num=1, worker_type="w", contract={"reward": 10})
    board.deliver(t.id, [str(tmp_path / "out.md")])
    assert board.tickets[t.id].status == TicketStatus.DELIVERED

    passed = board.verify(t.id, lambda x: (True, "good", 10.0))
    assert passed
    assert board.tickets[t.id].status == TicketStatus.VERIFIED
    assert board.tickets[t.id].reward == 10.0


def test_verify_reject_then_reissue(tmp_path: Path) -> None:
    board = _board(tmp_path)
    t = board.issue(round_num=1, worker_type="w", contract={"reward": 10})
    board.deliver(t.id, [])
    board.verify(t.id, lambda x: (False, "no output", 0))
    assert board.tickets[t.id].status == TicketStatus.REJECTED

    board.reissue(t.id, additional_feedback="please retry")
    assert board.tickets[t.id].status == TicketStatus.PENDING
    assert board.tickets[t.id].retry_count == 1
    assert "please retry" in board.tickets[t.id].feedback


def test_three_strike_escalation(tmp_path: Path) -> None:
    board = _board(tmp_path)
    t = board.issue(round_num=1, worker_type="w", contract={"reward": 10})
    # 3 reject+reissue cycles: retry_count goes 0→1→2→3
    for i in range(3):
        board.deliver(t.id, [])
        board.verify(t.id, lambda x: (False, f"fail {i}", 0))
        board.reissue(t.id, additional_feedback=f"retry {i+1}", retry_cap=3)
    assert board.tickets[t.id].retry_count == 3
    # 4th reject — reissue should raise (retry_count=3 ≥ cap=3)
    board.deliver(t.id, [])
    board.verify(t.id, lambda x: (False, "fail 4", 0))
    with pytest.raises(RuntimeError, match="retry cap"):
        board.reissue(t.id, retry_cap=3)


def test_round_summary(tmp_path: Path) -> None:
    board = _board(tmp_path)
    t1 = board.issue(round_num=1, worker_type="a", contract={"reward": 10})
    t2 = board.issue(round_num=1, worker_type="b", contract={"reward": 5})
    board.deliver(t1.id, [])
    board.verify(t1.id, lambda x: (True, "", 10))
    board.deliver(t2.id, [])
    board.verify(t2.id, lambda x: (False, "bad", 0))
    s = board.round_summary(1)
    assert s["total"] == 2
    assert s["by_status"]["verified"] == 1
    assert s["by_status"]["rejected"] == 1
    assert s["total_reward"] == 10


def test_persistence_across_load(tmp_path: Path) -> None:
    b1 = _board(tmp_path)
    t = b1.issue(round_num=1, worker_type="w", contract={"reward": 10})
    b1.deliver(t.id, ["/x.md"])
    b1.verify(t.id, lambda x: (True, "", 10))

    b2 = TicketBoard(tmp_path / "ticket-state.json")
    assert t.id in b2.tickets
    assert b2.tickets[t.id].status == TicketStatus.VERIFIED
    assert b2.tickets[t.id].reward == 10
