"""Tests for the provenance attestation + advisory filter (Phase-A: stamp + log/count).

Uses real schema-valid tickets written to tmp ledgers.  HOME is sandboxed so
local_key() creates the attest.key under tmp_path rather than the real ~/.claude.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _improvement as imp  # noqa: E402
import _learnings as lrn  # noqa: E402
import measure_learnings_injection as mi  # noqa: E402
from _improvement import Observation  # noqa: E402

NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_KEY_A = b"\x01" * 32
_KEY_B = b"\x02" * 32


# ---------------------------------------------------------------------------
# Ticket helpers (schema-valid, gate-passable)
# ---------------------------------------------------------------------------

def _base_ticket(fingerprint: str = "a" * 64, distinct_runs: int = 2) -> dict:
    return {
        "schema_version": 1,
        "fingerprint": fingerprint,
        "state": "candidate",
        "pattern": "worker skipped verify gate",
        "source": "reviewer-finding",
        "candidate_asset": "hook",
        "occurrences": distinct_runs,
        "distinct_runs": distinct_runs,
        "first_seen": "2026-06-15T00:00:00Z",
        "last_seen": "2026-06-15T00:00:00Z",
        "plugin_version": "0.9.0",
        "repo_fingerprint": "abc123",
        "evidence": [
            {"run_id": f"r{i}", "snippet": f"snip-{i}", "source_path": "hooks/foo.sh"}
            for i in range(1, distinct_runs + 1)
        ],
        "promotion_gate": {"tests_pass": None, "ci_pass": None, "user_approved": None},
    }


def _write_ticket(ledger: Path, ticket: dict) -> None:
    ledger.mkdir(parents=True, exist_ok=True)
    fp = ticket["fingerprint"]
    (ledger / f"{fp}.json").write_text(json.dumps(ticket, indent=2) + "\n")


# ---------------------------------------------------------------------------
# 1. Forged attestation → attestation-mismatch
# ---------------------------------------------------------------------------

def test_forged_ticket_filtered(tmp_path):
    """A ticket with a wrong attestation hex → (False, 'attestation-mismatch')."""
    ticket = _base_ticket("b" * 64)
    ticket["provenance"] = {
        "algo": "hmac-sha256",
        "attestation": "f" * 64,
        "signed_at": "2026-06-15T12:00:00Z",
        "identity_version": 1,
    }
    ok, reason = imp.verify_ticket_provenance(ticket, key=_KEY_A)
    assert ok is False
    assert reason == "attestation-mismatch"


def test_forged_ticket_in_measure(tmp_path, monkeypatch):
    """Forged ticket is counted in provenance_unverified + filtered_fingerprints."""
    monkeypatch.setenv("HOME", str(tmp_path))

    ledger = tmp_path / "ledger"
    ticket = _base_ticket("b" * 64)
    ticket["provenance"] = {
        "algo": "hmac-sha256",
        "attestation": "f" * 64,
        "signed_at": "2026-06-15T12:00:00Z",
        "identity_version": 1,
    }
    _write_ticket(ledger, ticket)

    result = mi.measure(ledger, ["hooks/"])
    assert result["provenance_unverified"] == 1
    assert result["provenance_verified"] == 0
    assert result["filtered_fingerprints"] == ["b" * 12]
    assert result["provenance_filtered_pct"] == 100.0


# ---------------------------------------------------------------------------
# 2. Inflated distinct_runs → distinct-runs-inflated
# ---------------------------------------------------------------------------

def test_inflated_distinct_runs_filtered(tmp_path):
    """One evidence row but distinct_runs=9 → (False, 'distinct-runs-inflated')."""
    ticket = _base_ticket("c" * 64, distinct_runs=1)
    ticket["distinct_runs"] = 9  # inflated: only 1 unique run_id in evidence
    imp.stamp_provenance(ticket, key=_KEY_A, now=NOW)  # stamp covers inflated value
    # After stamp, verify should catch the counts mismatch
    ok, reason = imp.verify_ticket_provenance(ticket, key=_KEY_A)
    assert ok is False
    assert reason == "distinct-runs-inflated"


# ---------------------------------------------------------------------------
# 3. Legitimately stamped ticket → verified
# ---------------------------------------------------------------------------

def test_legit_stamped_verified(tmp_path, monkeypatch):
    """A ticket stamped with local_key() passes verify_ticket_provenance."""
    monkeypatch.setenv("HOME", str(tmp_path))

    ticket = _base_ticket("d" * 64)
    key = imp.local_key()
    imp.stamp_provenance(ticket, key=key, now=NOW)

    ok, reason = imp.verify_ticket_provenance(ticket, key=key)
    assert ok is True
    assert reason == "verified"


def test_legit_stamped_passes_select_tickets(tmp_path, monkeypatch):
    """A legitimately stamped ticket still appears in select_tickets output."""
    monkeypatch.setenv("HOME", str(tmp_path))

    ledger = tmp_path / "ledger"
    ticket = _base_ticket("d" * 64)
    key = imp.local_key()
    imp.stamp_provenance(ticket, key=key, now=NOW)
    _write_ticket(ledger, ticket)

    matched = lrn.select_tickets(ledger, ["hooks/"])
    fps = [str(t["fingerprint"]) for t in matched]
    assert "d" * 64 in fps


# ---------------------------------------------------------------------------
# 4. Legacy unsigned ticket → grandfathered
# ---------------------------------------------------------------------------

def test_legacy_unsigned_grandfathered_non_strict():
    """No provenance field → (True, 'legacy-unsigned') in non-strict mode."""
    ticket = _base_ticket("e" * 64)
    ok, reason = imp.verify_ticket_provenance(ticket, key=_KEY_A, strict=False)
    assert ok is True
    assert reason == "legacy-unsigned"


def test_legacy_unsigned_rejected_strict():
    """No provenance field → (False, ...) in strict=True mode."""
    ticket = _base_ticket("e" * 64)
    ok, reason = imp.verify_ticket_provenance(ticket, key=_KEY_A, strict=True)
    assert ok is False
    assert reason == "legacy-unsigned"


def test_legacy_unsigned_counted_in_measure(tmp_path, monkeypatch):
    """Legacy ticket is counted in provenance_legacy_unsigned, not unverified."""
    monkeypatch.setenv("HOME", str(tmp_path))

    ledger = tmp_path / "ledger"
    ticket = _base_ticket("e" * 64)  # no provenance field
    _write_ticket(ledger, ticket)

    result = mi.measure(ledger, ["hooks/"])
    assert result["provenance_legacy_unsigned"] == 1
    assert result["provenance_unverified"] == 0
    assert result["provenance_verified"] == 0
    assert result["filtered_fingerprints"] == []


# ---------------------------------------------------------------------------
# 5. Advisory: forged ticket does NOT get dropped from select_tickets
# ---------------------------------------------------------------------------

def test_advisory_does_not_drop(tmp_path, monkeypatch):
    """A forged ticket is logged but still appears in select_tickets (advisory-only)."""
    monkeypatch.setenv("HOME", str(tmp_path))

    ledger = tmp_path / "ledger"
    ticket = _base_ticket("f" * 64)
    ticket["provenance"] = {
        "algo": "hmac-sha256",
        "attestation": "f" * 64,
        "signed_at": "2026-06-15T12:00:00Z",
        "identity_version": 1,
    }
    _write_ticket(ledger, ticket)

    matched = lrn.select_tickets(ledger, ["hooks/"])
    fps = [str(t["fingerprint"]) for t in matched]
    # Advisory: the forged ticket still appears in output
    assert "f" * 64 in fps


# ---------------------------------------------------------------------------
# 6. RED-evidence: flipping HMAC compare makes test_legit_stamped_verified fail
# ---------------------------------------------------------------------------

def test_red_wrong_key_fails_verification(tmp_path):
    """A ticket stamped with KEY_A does NOT verify under KEY_B — proves MAC matters."""
    ticket = _base_ticket("a" * 64)
    imp.stamp_provenance(ticket, key=_KEY_A, now=NOW)

    ok, reason = imp.verify_ticket_provenance(ticket, key=_KEY_B)
    assert ok is False
    assert reason == "attestation-mismatch"


# ---------------------------------------------------------------------------
# 7. local_key() is idempotent — second call returns the same bytes
# ---------------------------------------------------------------------------

def test_local_key_idempotent(tmp_path, monkeypatch):
    """local_key() returns the same bytes on repeated calls."""
    monkeypatch.setenv("HOME", str(tmp_path))

    k1 = imp.local_key()
    k2 = imp.local_key()
    assert k1 == k2
    assert len(k1) == 32


# ---------------------------------------------------------------------------
# 8. bump_or_create stamps a provenance on every write
# ---------------------------------------------------------------------------

def test_bump_or_create_stamps_provenance(tmp_path, monkeypatch):
    """bump_or_create produces a ticket with a valid provenance block."""
    monkeypatch.setenv("HOME", str(tmp_path))

    ledger = tmp_path / "ledger"
    obs = Observation("reviewer-finding", "foo.sh", "missing verify", "hook", "r1", "snip-1",
                      "hooks/foo.sh")
    ticket = imp.bump_or_create(ledger, obs, repo_root=tmp_path, now=NOW, dry_run=False)

    assert "provenance" in ticket
    key = imp.local_key()
    ok, reason = imp.verify_ticket_provenance(ticket, key=key)
    assert ok is True
    assert reason == "verified"


# ---------------------------------------------------------------------------
# 9. measure() provenance counts are JSON-serialisable
# ---------------------------------------------------------------------------

def test_measure_provenance_keys_json_serialisable(tmp_path, monkeypatch):
    """All new measure() provenance keys are present and JSON-serialisable."""
    monkeypatch.setenv("HOME", str(tmp_path))

    ledger = tmp_path / "ledger"
    ticket = _base_ticket("a" * 64)
    key = imp.local_key()
    imp.stamp_provenance(ticket, key=key, now=NOW)
    _write_ticket(ledger, ticket)

    result = mi.measure(ledger, ["hooks/"])
    dumped = json.dumps(result)  # must not raise
    loaded = json.loads(dumped)

    for k in ("provenance_verified", "provenance_legacy_unsigned",
               "provenance_unverified", "provenance_filtered_pct",
               "filtered_fingerprints"):
        assert k in loaded, f"key {k!r} missing from measure() result"

    assert loaded["provenance_verified"] == 1
    assert loaded["provenance_legacy_unsigned"] == 0
    assert loaded["provenance_unverified"] == 0
    assert loaded["provenance_filtered_pct"] == 0.0
    assert loaded["filtered_fingerprints"] == []
