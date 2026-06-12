"""Tests for scripts/_promotion.py — Hermes ticket FSM + promotion gates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _promotion import (  # noqa: E402
    GATE_FIELDS,
    TRANSITIONS,
    PromotionError,
    load_tickets,
    resolve_fingerprint,
    set_gate_field,
    transition,
)


def _seed_ticket(ledger: Path, fp: str, state: str = "candidate",
                 gates: dict | None = None) -> Path:
    ledger.mkdir(parents=True, exist_ok=True)
    ticket = {
        "schema_version": 1,
        "fingerprint": fp,
        "state": state,
        "pattern": "shellcheck",
        "source": "insight",
        "candidate_asset": "hook",
        "occurrences": 3,
        "distinct_runs": 3,
        "first_seen": "2026-06-10T08:00:39Z",
        "last_seen": "2026-06-12T23:06:46Z",
        "plugin_version": "0.8.7",
        "repo_fingerprint": "0378988721755a00",
        "evidence": [{"run_id": "r1", "snippet": "{}"}],
        "promotion_gate": gates or {
            "tests_pass": None, "ci_pass": None, "user_approved": None,
        },
    }
    path = ledger / f"{fp}.json"
    path.write_text(json.dumps(ticket))
    return path


FP_A = "a" * 64
FP_B = "ab" + "0" * 62


class TestLoadTickets:
    def test_empty_dir_returns_empty(self, tmp_path):
        assert load_tickets(tmp_path) == []

    def test_loads_and_validates(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        tickets = load_tickets(tmp_path)
        assert len(tickets) == 1
        assert tickets[0]["fingerprint"] == FP_A

    def test_skips_lock_files(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        (tmp_path / f"{FP_A}.json.lock").write_text("")
        assert len(load_tickets(tmp_path)) == 1

    def test_malformed_ticket_raises(self, tmp_path):
        (tmp_path / f"{FP_A}.json").write_text("{not json")
        with pytest.raises(PromotionError):
            load_tickets(tmp_path)


class TestResolveFingerprint:
    def test_unique_prefix_resolves(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        _seed_ticket(tmp_path, FP_B)
        assert resolve_fingerprint(tmp_path, "aa") == FP_A

    def test_ambiguous_prefix_raises(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        _seed_ticket(tmp_path, FP_B)
        with pytest.raises(PromotionError, match="ambiguous"):
            resolve_fingerprint(tmp_path, "a")

    def test_unknown_prefix_raises(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        with pytest.raises(PromotionError, match="no ticket"):
            resolve_fingerprint(tmp_path, "ffff")


class TestSetGateField:
    def test_sets_field_and_persists(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        out = set_gate_field(tmp_path, FP_A, "tests_pass", True)
        assert out["promotion_gate"]["tests_pass"] is True
        on_disk = json.loads((tmp_path / f"{FP_A}.json").read_text())
        assert on_disk["promotion_gate"]["tests_pass"] is True

    def test_rejects_unknown_field(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        with pytest.raises(PromotionError, match="gate field"):
            set_gate_field(tmp_path, FP_A, "vibes", True)


class TestTransition:
    def test_full_happy_path(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        for gate in GATE_FIELDS:
            set_gate_field(tmp_path, FP_A, gate, True)
        for state in ("accepted", "implemented", "verified", "promoted"):
            out = transition(tmp_path, FP_A, state)
            assert out["state"] == state

    def test_illegal_jump_raises(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        with pytest.raises(PromotionError, match="candidate -> promoted"):
            transition(tmp_path, FP_A, "promoted")

    def test_promoted_requires_all_gates_true(self, tmp_path):
        _seed_ticket(tmp_path, FP_A, state="verified", gates={
            "tests_pass": True, "ci_pass": True, "user_approved": None,
        })
        with pytest.raises(PromotionError, match="user_approved"):
            transition(tmp_path, FP_A, "promoted")

    def test_reject_allowed_from_any_live_state(self, tmp_path):
        for i, state in enumerate(("candidate", "accepted", "implemented", "verified")):
            fp = f"{i}" * 64
            _seed_ticket(tmp_path, fp, state=state)
            assert transition(tmp_path, fp, "rejected")["state"] == "rejected"

    def test_terminal_states_frozen(self, tmp_path):
        _seed_ticket(tmp_path, FP_A, state="rejected")
        with pytest.raises(PromotionError):
            transition(tmp_path, FP_A, "candidate")

    def test_transition_result_still_schema_valid(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        out = transition(tmp_path, FP_A, "accepted")
        from _improvement import validate_ticket
        validate_ticket(out)
