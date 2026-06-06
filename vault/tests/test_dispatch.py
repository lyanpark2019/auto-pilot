"""Tests for DispatchBoard — PM ticket lifecycle for drift-fix mode."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from pipeline.dispatch import DispatchBoard, TicketStatus


def _seed_plan(project: Path) -> None:
    vb = project / ".vault-builder"
    vb.mkdir(parents=True, exist_ok=True)
    (vb / "fix-plan.json").write_text(json.dumps({
        "tickets": [
            {"id": "T1", "worker_type": "vault-knowledge-author",
             "contract": {"drift_type": "gap", "items": [{"module": "src/a.py"}, {"module": "src/b.py"}]}},
            {"id": "T2", "worker_type": "vault-knowledge-author",
             "contract": {"drift_type": "claim_drift", "items": [{"symbol": "x"}]}},
        ]
    }))


def test_load_plan_creates_pending_tickets(tmp_path: Path) -> None:
    _seed_plan(tmp_path)
    b = DispatchBoard(tmp_path)
    pending = b.pending_tickets()
    assert {t.id for t in pending} == {"T1", "T2"}
    assert (tmp_path / ".vault-builder" / "dispatch-state.json").exists()


def test_dispatch_deliver_verify(tmp_path: Path) -> None:
    _seed_plan(tmp_path)
    b = DispatchBoard(tmp_path)
    b.mark_dispatched("T1")
    assert b.tickets["T1"].status == TicketStatus.DISPATCHED.value
    b.deliver("T1", ["docs/a.md", "docs/b.md"])
    assert b.tickets["T1"].status == TicketStatus.DELIVERED.value
    passed, msg = b.verify("T1", lambda t: (True, "ok"))
    assert passed
    assert b.tickets["T1"].status == TicketStatus.VERIFIED.value


def test_reissue_increments_retry(tmp_path: Path) -> None:
    _seed_plan(tmp_path)
    b = DispatchBoard(tmp_path)
    b.deliver("T1", [])
    b.verify("T1", lambda t: (False, "no output"))
    b.reissue("T1", additional_feedback="please retry")
    assert b.tickets["T1"].status == TicketStatus.PENDING.value
    assert b.tickets["T1"].retry_count == 1
    assert "please retry" in b.tickets["T1"].feedback


def test_three_strike_escalates(tmp_path: Path) -> None:
    _seed_plan(tmp_path)
    b = DispatchBoard(tmp_path)
    for i in range(3):
        b.deliver("T1", [])
        b.verify("T1", lambda t: (False, f"fail {i}"))
        b.reissue("T1", additional_feedback=f"retry {i+1}")
    assert b.tickets["T1"].retry_count == 3
    b.deliver("T1", [])
    b.verify("T1", lambda t: (False, "fail 4"))
    with pytest.raises(RuntimeError, match="strikes"):
        b.reissue("T1")
    assert b.tickets["T1"].status == TicketStatus.ESCALATED.value


def test_persistence_across_load(tmp_path: Path) -> None:
    _seed_plan(tmp_path)
    b1 = DispatchBoard(tmp_path)
    b1.deliver("T1", ["docs/a.md"])
    b1.verify("T1", lambda t: (True, "ok"))
    b2 = DispatchBoard(tmp_path)
    assert b2.tickets["T1"].status == TicketStatus.VERIFIED.value


def test_summary(tmp_path: Path) -> None:
    _seed_plan(tmp_path)
    b = DispatchBoard(tmp_path)
    b.deliver("T1", ["x"])
    b.verify("T1", lambda t: (True, ""))
    s = b.summary()
    assert s["total"] == 2
    assert s["by_status"][TicketStatus.VERIFIED.value] == 1
    assert s["by_status"][TicketStatus.PENDING.value] == 1
