"""Tests for scripts/measure_learnings_injection.py.

Uses REAL schema-valid tickets (dicts that pass _improvement.validate_ticket)
seeded into a temp ledger.  Runs the real measure() — no mocking of internals.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import measure_learnings_injection as mi  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evidence_entry(run_id: str = "run-1", snippet: str = "worker skipped verify",
                    source_path: str = "") -> dict:
    entry: dict = {"run_id": run_id, "snippet": snippet}
    if source_path:
        entry["source_path"] = source_path
    return entry


def _valid_ticket(
    fingerprint: str = "a" * 64,
    state: str = "candidate",
    source_path: str = "hooks/foo.sh",
    run_id: str = "run-1",
    snippet: str = "worker skipped verify",
    distinct_runs: int = 2,
    source: str = "reviewer-finding",
) -> dict:
    """Return a schema-valid improvement ticket.

    ``state="candidate"`` + ``distinct_runs=2`` + ``source="reviewer-finding"``
    passes ``is_promotable()`` (threshold = 2) — the gate-passed condition.
    """
    t: dict = {
        "schema_version": 1,
        "fingerprint": fingerprint,
        "state": state,
        "pattern": "worker skipped verify gate",
        "source": source,
        "candidate_asset": "hook",
        "occurrences": distinct_runs,
        "distinct_runs": distinct_runs,
        "first_seen": "2026-06-09T00:00:00Z",
        "last_seen": "2026-06-10T00:00:00Z",
        "plugin_version": "0.9.0",
        "repo_fingerprint": "abc123",
        "evidence": [_evidence_entry(run_id=run_id, snippet=snippet,
                                     source_path=source_path)],
        "promotion_gate": {"tests_pass": None, "ci_pass": None, "user_approved": None},
    }
    return t


def _write_ticket(ledger: Path, ticket: dict) -> None:
    ledger.mkdir(parents=True, exist_ok=True)
    fp = ticket["fingerprint"]
    (ledger / f"{fp}.json").write_text(json.dumps(ticket, indent=2) + "\n")


# ---------------------------------------------------------------------------
# 1. File-anchored promotable ticket + matching scope
# ---------------------------------------------------------------------------

def test_file_anchored_matches_scope(tmp_path):
    """A gate-passed ticket with source_path in hooks/ is injected for hooks/ scope."""
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(fingerprint="a" * 64, state="candidate", distinct_runs=2,
                           source_path="hooks/foo.sh")
    _write_ticket(ledger, ticket)

    result = mi.measure(ledger, ["hooks/"])

    assert result["gate_passed_total"] == 1
    assert result["file_anchored"] == 1
    assert result["scope_blind"] == 0
    assert result["matched_per_scope"]["hooks/"] == 1
    assert result["injected_any_scope"] == 1
    assert result["scope_addressable_pct"] == 100.0
    assert result["scope_blind_fingerprints"] == []


# ---------------------------------------------------------------------------
# 2. File-less (scope-blind) promotable ticket
# ---------------------------------------------------------------------------

def test_fileless_ticket_is_scope_blind(tmp_path):
    """A gate-passed ticket with no source_path is scope-blind."""
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(fingerprint="b" * 64, state="candidate", distinct_runs=2,
                           source_path="")  # no file reference
    _write_ticket(ledger, ticket)

    result = mi.measure(ledger, ["hooks/"])

    assert result["gate_passed_total"] == 1
    assert result["file_anchored"] == 0
    assert result["scope_blind"] == 1
    assert result["injected_any_scope"] == 0
    assert result["scope_addressable_pct"] == 0.0
    assert result["scope_blind_fingerprints"] == ["b" * 12]


# ---------------------------------------------------------------------------
# 3. Mix: 1 file-anchored (matching) + 1 file-less
# ---------------------------------------------------------------------------

def test_mix_half_scope_addressable(tmp_path):
    """1 file-anchored matching ticket + 1 file-less → 50% scope_addressable_pct."""
    ledger = tmp_path / "ledger"
    _write_ticket(ledger, _valid_ticket(fingerprint="a" * 64, state="candidate",
                                        distinct_runs=2, source_path="hooks/bar.sh"))
    _write_ticket(ledger, _valid_ticket(fingerprint="c" * 64, state="candidate",
                                        distinct_runs=2, source_path=""))

    result = mi.measure(ledger, ["hooks/"])

    assert result["gate_passed_total"] == 2
    assert result["file_anchored"] == 1
    assert result["scope_blind"] == 1
    assert result["injected_any_scope"] == 1
    assert result["scope_addressable_pct"] == 50.0


# ---------------------------------------------------------------------------
# 4. Absent ledger → all zeros
# ---------------------------------------------------------------------------

def test_absent_ledger_all_zeros(tmp_path):
    """Non-existent ledger directory → all zero counts, empty lists."""
    missing = tmp_path / "does_not_exist"
    result = mi.measure(missing, ["scripts/"])

    assert result["gate_passed_total"] == 0
    assert result["file_anchored"] == 0
    assert result["scope_blind"] == 0
    assert result["injected_any_scope"] == 0
    assert result["scope_addressable_pct"] == 0.0
    assert result["scope_blind_fingerprints"] == []
    assert result["matched_per_scope"] == {"scripts/": 0}


# ---------------------------------------------------------------------------
# 5. File-anchored ticket whose path does NOT match the scope
# ---------------------------------------------------------------------------

def test_file_anchored_but_wrong_scope(tmp_path):
    """file_anchored=1 but scope is wrong → injected_any_scope=0."""
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(fingerprint="d" * 64, state="candidate", distinct_runs=2,
                           source_path="scripts/orchestrator.py")
    _write_ticket(ledger, ticket)

    # scope is hooks/ but evidence is scripts/ — no match
    result = mi.measure(ledger, ["hooks/"])

    assert result["file_anchored"] == 1
    assert result["scope_blind"] == 0
    assert result["injected_any_scope"] == 0
    assert result["scope_addressable_pct"] == 0.0
    assert result["matched_per_scope"]["hooks/"] == 0
    # not scope_blind (has a file), just not matched by this scope
    assert result["scope_blind_fingerprints"] == []


# ---------------------------------------------------------------------------
# 6. JSON serialisability of the full result dict
# ---------------------------------------------------------------------------

def test_result_is_json_serialisable(tmp_path):
    """measure() result must be json.dumps-able (the CLI --json contract)."""
    ledger = tmp_path / "ledger"
    _write_ticket(ledger, _valid_ticket(fingerprint="e" * 64, state="candidate",
                                        distinct_runs=2, source_path="hooks/x.sh"))
    result = mi.measure(ledger, ["hooks/"])
    dumped = json.dumps(result)  # must not raise
    loaded = json.loads(dumped)
    assert loaded["gate_passed_total"] == 1
