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


# ---------------------------------------------------------------------------
# A/B corpus fixture helpers
# ---------------------------------------------------------------------------

def _ticket_with_bad_provenance(fingerprint: str, source_path: str) -> dict:
    """Gate-passed ticket with a present-but-invalid provenance block.

    The HMAC attestation is set to all-f's (64 hex chars — schema-valid but
    will fail verify_ticket_provenance → unverified bucket).
    """
    t = _valid_ticket(fingerprint=fingerprint, state="candidate",
                      distinct_runs=2, source_path=source_path)
    t["provenance"] = {
        "algo": "hmac-sha256",
        "attestation": "f" * 64,
        "signed_at": "2026-06-15T00:00:00Z",
        "identity_version": 1,
    }
    return t


def _build_ab_corpus(ledger: Path) -> None:
    """Seed the ledger with a corpus that exercises every compare_gating bucket.

    Scope used: ``scripts/`` (dir prefix match for all evidence).

    Tickets:
      promoted_a   — promoted, gate-passed; in BOTH arms
      candidate_a  — candidate reviewer-finding distinct_runs=2; gate-passed; BOTH arms
      subthresh_a  — candidate reviewer-finding distinct_runs=1; NOT gate-passed → not_promotable
      rejected_a   — rejected distinct_runs=2; NOT gate-passed (excluded_state)
      quarantined_a— quarantined distinct_runs=2; NOT gate-passed (excluded_state)
      blind_a      — gate-passed but no source_path → scope-blind; neither arm injects it
      bad_prov_a   — gate-passed + scope-matched + invalid provenance → unverified bucket
    """
    promoted = _valid_ticket(fingerprint="1" * 64, state="promoted",
                             source_path="scripts/foo.py", distinct_runs=2)
    promoted["promotion_gate"] = {"tests_pass": True, "ci_pass": True, "user_approved": True}
    _write_ticket(ledger, promoted)

    _write_ticket(ledger, _valid_ticket(fingerprint="2" * 64, state="candidate",
                                        distinct_runs=2, source_path="scripts/bar.py"))

    _write_ticket(ledger, _valid_ticket(fingerprint="3" * 64, state="candidate",
                                        distinct_runs=1, source_path="scripts/baz.py"))

    _write_ticket(ledger, _valid_ticket(fingerprint="4" * 64, state="rejected",
                                        distinct_runs=2, source_path="scripts/rej.py"))

    _write_ticket(ledger, _valid_ticket(fingerprint="5" * 64, state="quarantined",
                                        distinct_runs=2, source_path="scripts/qua.py"))

    _write_ticket(ledger, _valid_ticket(fingerprint="6" * 64, state="candidate",
                                        distinct_runs=2, source_path=""))

    _write_ticket(ledger, _ticket_with_bad_provenance(fingerprint="7" * 64,
                                                      source_path="scripts/prov.py"))


# ---------------------------------------------------------------------------
# 7. compare_gating — filtered_total and breakdown
# ---------------------------------------------------------------------------

def test_compare_gating_filtered_total_and_breakdown(tmp_path):
    """compare_gating must correctly count the filtered set and bucket by reason."""
    ledger = tmp_path / "ledger"
    _build_ab_corpus(ledger)

    result = mi.compare_gating(ledger, ["scripts/"])

    # Gated arm: promoted + candidate_pass + bad_prov = 3 scope-matched gate-passed
    # Ungated arm: all 5 scope-matched (promoted, candidate_pass, subthresh, rejected,
    #              quarantined, bad_prov) = 6 (blind has no source_path → excluded both arms)
    # filtered = 3 (subthresh + rejected + quarantined)
    assert result["filtered_total"] == 3

    bd = result["filtered_breakdown"]
    # rejected + quarantined → excluded_state = 2
    assert bd["excluded_state"] == 2
    # subthresh → not_promotable = 1
    assert bd["not_promotable"] == 1


# ---------------------------------------------------------------------------
# 8. compare_gating — provenance arms
# ---------------------------------------------------------------------------

def test_compare_gating_provenance_arms(tmp_path):
    """gated_provenance.unverified >= 1; ungated_provenance.unverified >= gated."""
    ledger = tmp_path / "ledger"
    _build_ab_corpus(ledger)

    result = mi.compare_gating(ledger, ["scripts/"])

    gp = result["gated_provenance"]
    up = result["ungated_provenance"]

    assert gp["unverified"] >= 1, "bad_prov ticket is gate-passed → unverified in gated arm"
    assert up["unverified"] >= gp["unverified"], (
        "ungated arm includes all gated unverified plus potentially more"
    )


# ---------------------------------------------------------------------------
# 9. measure_delta shape and injected_any_scope.delta > 0
# ---------------------------------------------------------------------------

def test_measure_delta_shape_and_delta_positive(tmp_path):
    """measure_delta returns {a, b, delta} scalars and ungated injects more."""
    ledger = tmp_path / "ledger"
    _build_ab_corpus(ledger)

    gated = mi.measure(ledger, ["scripts/"], gated=True)
    ungated = mi.measure(ledger, ["scripts/"], gated=False)
    delta = mi.measure_delta(gated, ungated)

    for key in mi._SCALAR_KEYS:
        assert key in delta, f"missing key {key!r} in measure_delta output"
        row = delta[key]
        assert "a" in row and "b" in row and "delta" in row

    assert delta["injected_any_scope"]["delta"] > 0, (
        "ungated must inject more than gated for this corpus"
    )


# ---------------------------------------------------------------------------
# 10. compare_gating — JSON byte-stability across ledger write order
# ---------------------------------------------------------------------------

def test_compare_gating_byte_stable_across_write_order(tmp_path):
    """compare_gating JSON output is identical regardless of ledger write order."""
    ledger_a = tmp_path / "ledger_a"
    ledger_b = tmp_path / "ledger_b"

    _build_ab_corpus(ledger_a)

    # Write the same tickets in reversed fingerprint order
    tickets = [
        _valid_ticket(fingerprint="1" * 64, state="promoted", source_path="scripts/foo.py",
                      distinct_runs=2),
        _valid_ticket(fingerprint="2" * 64, state="candidate", distinct_runs=2,
                      source_path="scripts/bar.py"),
        _valid_ticket(fingerprint="3" * 64, state="candidate", distinct_runs=1,
                      source_path="scripts/baz.py"),
        _valid_ticket(fingerprint="4" * 64, state="rejected", distinct_runs=2,
                      source_path="scripts/rej.py"),
        _valid_ticket(fingerprint="5" * 64, state="quarantined", distinct_runs=2,
                      source_path="scripts/qua.py"),
        _valid_ticket(fingerprint="6" * 64, state="candidate", distinct_runs=2,
                      source_path=""),
        _ticket_with_bad_provenance(fingerprint="7" * 64, source_path="scripts/prov.py"),
    ]
    tickets[0]["promotion_gate"] = {"tests_pass": True, "ci_pass": True, "user_approved": True}
    for t in reversed(tickets):
        _write_ticket(ledger_b, t)

    out_a = json.dumps(mi.compare_gating(ledger_a, ["scripts/"]), sort_keys=True)
    out_b = json.dumps(mi.compare_gating(ledger_b, ["scripts/"]), sort_keys=True)
    assert out_a == out_b, "compare_gating must be byte-stable across write order"


# ---------------------------------------------------------------------------
# 11. RED-proof: reverting gated=False to behave like gated=True breaks assertions
# ---------------------------------------------------------------------------

def test_red_proof_gated_false_differs_from_gated_true(tmp_path):
    """If the gated=False branch behaves identically to gated=True, this must FAIL.

    The assertion ``filtered_total >= 1`` and ``delta["injected_any_scope"]["delta"] >= 1``
    together prove the gated=False branch actually skips the gate.  A revert of that
    branch would make compare_gating return filtered_total=0 and delta=0, flipping this test.
    """
    ledger = tmp_path / "ledger"
    _build_ab_corpus(ledger)

    result = mi.compare_gating(ledger, ["scripts/"])
    gated = mi.measure(ledger, ["scripts/"], gated=True)
    ungated = mi.measure(ledger, ["scripts/"], gated=False)
    delta = mi.measure_delta(gated, ungated)

    # These two lines MUST remain true — if gated=False == gated=True they both flip to False
    assert result["filtered_total"] >= 1, (
        "corpus contains sub-threshold and excluded-state tickets that must be filtered"
    )
    assert delta["injected_any_scope"]["delta"] >= 1, (
        "ungated must inject at least 1 more ticket than gated for this corpus"
    )
