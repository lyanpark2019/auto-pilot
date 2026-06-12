"""Regression pins for PM contract dispatch protocol.

These tests protect the evidence chain documented after the 2026-06-12
live smoke: PM-SIGNATURE must be followed by dispatch-contract-check before
any subagent ticket is prepared, and live dispatch prompts must carry literal
TICKET/contract_dir markers.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PM_ORCHESTRATOR = ROOT / "agents" / "pm-orchestrator.md"


def _contract_dispatch_protocol() -> str:
    text = PM_ORCHESTRATOR.read_text()
    start = text.index("## Contract dispatch protocol (v1)")
    end = text.index("## Merge conflict state machine (v1)")
    return text[start:end]


def test_pm_protocol_runs_contract_check_before_ticket_prep() -> None:
    section = _contract_dispatch_protocol()
    contract_check = "orchestrator.py dispatch-contract-check --contract"
    ticket_prep = "_dispatch.prepare_subagent_ticket"

    assert contract_check in section
    assert ticket_prep in section
    assert section.index(contract_check) < section.index(ticket_prep)


def test_pm_protocol_pins_ticket_and_contract_dir_markers() -> None:
    section = _contract_dispatch_protocol()

    assert "TICKET={ticket_path}" in section
    assert "contract_dir={contract_dir}" in section
