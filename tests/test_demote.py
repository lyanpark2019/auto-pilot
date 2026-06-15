"""Tests for the eviction / demotion path.

Covers: improvements-downvote, improvements-reinstate CLI verbs,
_learnings exclusion of quarantined, measure_learnings_injection new keys.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _promotion import (  # noqa: E402
    DEMOTION_THRESHOLD,
    GATE_FIELDS,
    PromotionError,
    PromotionGateUnmet,
    Ticket,
    _locked_update,
    resolve_fingerprint,
    transition,
)
from _learnings import is_gate_passed, select_tickets  # noqa: E402
from measure_learnings_injection import measure  # noqa: E402

import orchestrator  # type: ignore[import-not-found]  # noqa: E402

FP_A = "a" * 64
FP_B = "b" * 64

_FULL_GATE = {"tests_pass": True, "ci_pass": True, "user_approved": True}


def _seed_promoted(ledger: Path, fp: str = FP_A, extra: dict | None = None) -> Path:
    """Write a promoted ticket to the ledger (all gates True)."""
    ledger.mkdir(parents=True, exist_ok=True)
    ticket: dict = {
        "schema_version": 1,
        "fingerprint": fp,
        "state": "promoted",
        "pattern": "shellcheck",
        "source": "reviewer-finding",
        "candidate_asset": "hook",
        "occurrences": 3,
        "distinct_runs": 3,
        "first_seen": "2026-06-10T08:00:39Z",
        "last_seen": "2026-06-12T23:06:46Z",
        "plugin_version": "0.8.7",
        "repo_fingerprint": "0378988721755a00",
        "evidence": [{"run_id": "r1", "snippet": "check", "source_path": "scripts/foo.py"}],
        "promotion_gate": dict(_FULL_GATE),
    }
    if extra:
        ticket.update(extra)
    path = ledger / f"{fp}.json"
    path.write_text(json.dumps(ticket))
    return path


def _run(argv: list[str]) -> int:
    return orchestrator.main(argv)


def _make_ledger_and_repo(tmp_path: Path) -> tuple[Path, Path]:
    slug = str(tmp_path / "repo").replace("/", "-")
    ledger = tmp_path / "home" / ".claude" / "projects" / slug / "improvements"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    return ledger, repo_root


# ---------------------------------------------------------------------------
# Core: downvote × 2 distinct run-ids → quarantined
# ---------------------------------------------------------------------------

class TestDownvoteToQuarantine:
    def test_two_distinct_run_ids_quarantines(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        ledger, repo = _make_ledger_and_repo(tmp_path)
        _seed_promoted(ledger)

        rc1 = _run([
            "improvements-downvote", "--repo-root", str(repo),
            FP_A[:8], "--reason", "hurt", "--run-id", "run-1",
        ])
        assert rc1 == 0
        out1 = json.loads(capsys.readouterr().out)
        # One distinct run — below threshold → still promoted
        assert out1["state"] == "promoted"
        assert out1["harmful_count"] == 1

        rc2 = _run([
            "improvements-downvote", "--repo-root", str(repo),
            FP_A[:8], "--reason", "hurt again", "--run-id", "run-2",
        ])
        assert rc2 == 0
        out2 = json.loads(capsys.readouterr().out)
        # Two distinct runs → threshold (2) reached → quarantined
        assert out2["state"] == "quarantined"
        assert out2["harmful_count"] == 2

        # Verify disk state
        on_disk = json.loads((ledger / f"{FP_A}.json").read_text())
        assert on_disk["state"] == "quarantined"
        assert len(on_disk["demotions"]) == 2

    def test_same_run_id_twice_does_not_quarantine(self, tmp_path, monkeypatch, capsys):
        """Same run_id submitted twice counts as ONE distinct harmful run (below threshold)."""
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        ledger, repo = _make_ledger_and_repo(tmp_path)
        _seed_promoted(ledger)

        for _ in range(2):
            _run([
                "improvements-downvote", "--repo-root", str(repo),
                FP_A[:8], "--reason", "repeated", "--run-id", "run-same",
            ])
            capsys.readouterr()

        on_disk = json.loads((ledger / f"{FP_A}.json").read_text())
        # Same run_id de-duped → harmful_count == 1 (below DEMOTION_THRESHOLD=2)
        assert on_disk["harmful_count"] == 1
        assert on_disk["state"] == "promoted"

    def test_force_flag_immediate_quarantine(self, tmp_path, monkeypatch, capsys):
        """--force quarantines immediately regardless of harmful_count."""
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        ledger, repo = _make_ledger_and_repo(tmp_path)
        _seed_promoted(ledger)

        rc = _run([
            "improvements-downvote", "--repo-root", str(repo),
            FP_A[:8], "--reason", "urgent", "--force",
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["state"] == "quarantined"
        assert out["harmful_count"] == 1  # one manual (no run_id)

    def test_no_run_id_counts_as_manual_signal(self, tmp_path, monkeypatch, capsys):
        """Entries without run_id each contribute +1 to harmful_count."""
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        ledger, repo = _make_ledger_and_repo(tmp_path)
        _seed_promoted(ledger)

        # Two no-run_id entries → harmful_count == 2 → quarantined
        for i in range(DEMOTION_THRESHOLD):
            _run([
                "improvements-downvote", "--repo-root", str(repo),
                FP_A[:8], "--reason", f"manual {i}",
            ])
            capsys.readouterr()

        on_disk = json.loads((ledger / f"{FP_A}.json").read_text())
        assert on_disk["harmful_count"] == DEMOTION_THRESHOLD
        assert on_disk["state"] == "quarantined"

    def test_single_downvote_stays_promoted(self, tmp_path, monkeypatch, capsys):
        """One distinct run_id is below threshold — ticket stays promoted."""
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        ledger, repo = _make_ledger_and_repo(tmp_path)
        _seed_promoted(ledger)

        rc = _run([
            "improvements-downvote", "--repo-root", str(repo),
            FP_A[:8], "--reason", "once", "--run-id", "only-run",
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["state"] == "promoted"
        assert out["harmful_count"] == 1


# ---------------------------------------------------------------------------
# RED proof: quarantined excluded from injection
# ---------------------------------------------------------------------------

class TestQuarantinedExcludedFromInjection:
    def test_quarantined_excluded_from_select_tickets(self, tmp_path):
        """quarantined ticket must NOT appear in select_tickets output."""
        ledger = tmp_path / "improvements"
        _seed_promoted(ledger)
        # Transition to quarantined
        transition(ledger, FP_A, "quarantined")

        tickets = select_tickets(ledger, ["scripts/"])
        assert not any(t.get("fingerprint") == FP_A for t in tickets), (
            "quarantined ticket must be excluded from injection"
        )

    def test_quarantined_excluded_from_is_gate_passed(self, tmp_path):
        """is_gate_passed returns False for quarantined tickets."""
        ticket: Ticket = {
            "schema_version": 1,
            "fingerprint": FP_A,
            "state": "quarantined",
            "pattern": "x",
            "source": "reviewer-finding",
            "candidate_asset": None,
            "occurrences": 3,
            "distinct_runs": 3,
            "first_seen": "2026-06-10T00:00:00Z",
            "last_seen": "2026-06-10T00:00:00Z",
            "plugin_version": "0",
            "repo_fingerprint": "x",
            "evidence": [{"run_id": "r1", "snippet": "s"}],
            "promotion_gate": dict(_FULL_GATE),
        }
        assert is_gate_passed(ticket) is False

    def test_promoted_appears_in_select_tickets(self, tmp_path):
        """Promoted ticket with scope-matching evidence IS included."""
        ledger = tmp_path / "improvements"
        _seed_promoted(ledger)
        tickets = select_tickets(ledger, ["scripts/"])
        assert any(t.get("fingerprint") == FP_A for t in tickets)

    def test_revert_exclusion_reappears(self, tmp_path):
        """RED proof: if _EXCLUDED_STATES did not contain quarantined, ticket reappears.

        We monkey-patch _learnings._EXCLUDED_STATES to remove quarantined and
        verify the ticket comes back — proving the exclusion is what blocks it.
        """
        import _learnings as _ll

        ledger = tmp_path / "improvements"
        _seed_promoted(ledger)
        transition(ledger, FP_A, "quarantined")

        # With quarantined excluded → not found
        assert not select_tickets(ledger, ["scripts/"])

        original = _ll._EXCLUDED_STATES
        try:
            # Temporarily remove quarantined from excluded set (RED state)
            _ll._EXCLUDED_STATES = frozenset({"rejected"})
            tickets = select_tickets(ledger, ["scripts/"])
            assert any(t.get("fingerprint") == FP_A for t in tickets), (
                "without exclusion, quarantined ticket should re-appear"
            )
        finally:
            _ll._EXCLUDED_STATES = original


# ---------------------------------------------------------------------------
# Reinstate: quarantined → promoted, harmful_count reset
# ---------------------------------------------------------------------------

class TestReinstate:
    def test_reinstate_quarantined_to_promoted(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        ledger, repo = _make_ledger_and_repo(tmp_path)
        _seed_promoted(ledger)

        # Quarantine first
        _run([
            "improvements-downvote", "--repo-root", str(repo),
            FP_A[:8], "--reason", "oops", "--force",
        ])
        capsys.readouterr()

        rc = _run([
            "improvements-reinstate", "--repo-root", str(repo),
            FP_A[:8], "--reason", "false alarm",
        ])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["state"] == "promoted"

        on_disk = json.loads((ledger / f"{FP_A}.json").read_text())
        assert on_disk["state"] == "promoted"
        assert on_disk["harmful_count"] == 0
        assert len(on_disk["reinstatements"]) == 1
        assert on_disk["reinstatements"][0]["reason"] == "false alarm"

    def test_reinstate_re_applies_promotion_gate(self, tmp_path, monkeypatch, capsys):
        """Reinstate re-checks the promotion gate; fails if gate not all-True."""
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        ledger, repo = _make_ledger_and_repo(tmp_path)
        # Quarantined ticket with an unmet gate
        _seed_promoted(ledger, extra={
            "state": "quarantined",
            "promotion_gate": {"tests_pass": None, "ci_pass": True, "user_approved": True},
        })

        rc = _run([
            "improvements-reinstate", "--repo-root", str(repo), FP_A[:8],
        ])
        assert rc == 1  # gate unmet

    def test_reinstate_non_quarantined_fails(self, tmp_path, monkeypatch, capsys):
        """Reinstating a non-quarantined ticket (e.g. promoted) is an error."""
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        ledger, repo = _make_ledger_and_repo(tmp_path)
        _seed_promoted(ledger)  # already promoted, not quarantined

        rc = _run([
            "improvements-reinstate", "--repo-root", str(repo), FP_A[:8],
        ])
        assert rc == 1  # cannot reinstate a non-quarantined ticket
        capsys.readouterr()


# ---------------------------------------------------------------------------
# measure() new keys
# ---------------------------------------------------------------------------

class TestMeasureNewKeys:
    def _make_ledger(self, tmp_path: Path) -> Path:
        ledger = tmp_path / "improvements"
        return ledger

    def test_empty_ledger_has_new_keys(self, tmp_path):
        """Empty ledger returns zero values for all new keys."""
        ledger = self._make_ledger(tmp_path)
        result = measure(ledger, ["scripts/"])
        assert result["quarantined_total"] == 0
        assert result["demoted_excluded_from_injection"] == 0
        assert result["harmful_pending"] == 0
        assert result["reinstated_total"] == 0

    def test_quarantined_total_counted(self, tmp_path):
        ledger = self._make_ledger(tmp_path)
        _seed_promoted(ledger)
        transition(ledger, FP_A, "quarantined")

        result = measure(ledger, ["scripts/"])
        assert result["quarantined_total"] == 1
        assert result["gate_passed_total"] == 0  # quarantined excluded from gate_passed

    def test_demoted_excluded_from_injection(self, tmp_path):
        """demoted_excluded_from_injection counts quarantined tickets matching scope."""
        ledger = self._make_ledger(tmp_path)
        _seed_promoted(ledger)
        transition(ledger, FP_A, "quarantined")

        result = measure(ledger, ["scripts/"])
        assert result["demoted_excluded_from_injection"] == 1

    def test_harmful_pending(self, tmp_path):
        """harmful_pending counts non-quarantined tickets with 0 < harmful_count < threshold."""
        ledger = self._make_ledger(tmp_path)
        _seed_promoted(ledger)
        # Add one demotion signal but not enough to quarantine
        path = ledger / f"{FP_A}.json"
        ticket = json.loads(path.read_text())
        ticket["harmful_count"] = 1
        ticket["demotions"] = [{"reason": "r", "at": "2026-06-15T00:00:00Z", "signal": "downvote"}]
        path.write_text(json.dumps(ticket))

        result = measure(ledger, ["scripts/"])
        assert result["harmful_pending"] == 1

    def test_reinstated_total(self, tmp_path):
        ledger = self._make_ledger(tmp_path)
        _seed_promoted(ledger, extra={"reinstatements": [{"at": "2026-06-15T00:00:00Z"}]})

        result = measure(ledger, ["scripts/"])
        assert result["reinstated_total"] == 1

    def test_threshold_boundary(self, tmp_path):
        """harmful_count == DEMOTION_THRESHOLD is NOT in harmful_pending (it triggers quarantine)."""
        ledger = self._make_ledger(tmp_path)
        _seed_promoted(ledger)
        path = ledger / f"{FP_A}.json"
        ticket = json.loads(path.read_text())
        # At threshold but still promoted (edge case: someone manually set it without quarantine)
        ticket["harmful_count"] = DEMOTION_THRESHOLD
        path.write_text(json.dumps(ticket))

        result = measure(ledger, ["scripts/"])
        # harmful_count >= DEMOTION_THRESHOLD → not harmful_pending (condition is strictly <)
        assert result["harmful_pending"] == 0
