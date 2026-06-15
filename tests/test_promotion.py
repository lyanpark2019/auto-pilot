"""Tests for scripts/_promotion.py — Hermes ticket FSM + promotion gates.

Also covers orchestrator.py CLI shims: improvements-list, improvements-gate,
improvements-set-state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from _promotion import (  # noqa: E402
    GATE_FIELDS,
    PromotionError,
    Ticket,
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

    def test_partial_mode_skips_corrupt_returns_valid(self, tmp_path, capsys):
        """partial=True skips malformed tickets; default still raises; mutate still raises."""
        _seed_ticket(tmp_path, FP_A)
        corrupt_fp = "c" * 64
        (tmp_path / f"{corrupt_fp}.json").write_text("{not json")

        # RED: partial=True must return only the valid ticket and warn on stderr
        result = load_tickets(tmp_path, partial=True)
        assert len(result) == 1
        assert result[0]["fingerprint"] == FP_A
        captured = capsys.readouterr()
        assert "warning" in captured.err.lower()
        assert corrupt_fp[:8] in captured.err or "malformed" in captured.err.lower()
        # warning must NOT leak to stdout — improvements-list --json writes JSON there
        assert captured.out == ""

        # GREEN characterization: default=False still raises on malformed ledger
        with pytest.raises(PromotionError):
            load_tickets(tmp_path)

        # GREEN characterization: mutate/resolve on corrupt fingerprint still raises
        with pytest.raises(PromotionError):
            set_gate_field(tmp_path, corrupt_fp, "tests_pass", True)


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

    def test_corrupt_ticket_raises_promotion_error(self, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / f"{FP_A}.json").write_text("{not json")
        with pytest.raises(PromotionError, match="corrupt"):
            set_gate_field(tmp_path, FP_A, "tests_pass", True)

    def test_terminal_state_quarantined_blocks_gate(self, tmp_path):
        """quarantined is a terminal state — gate mutations are denied."""
        _seed_ticket(tmp_path, FP_A, state="quarantined",
                     gates={"tests_pass": True, "ci_pass": True, "user_approved": True})
        with pytest.raises(PromotionError, match="terminal"):
            set_gate_field(tmp_path, FP_A, "tests_pass", False)

    def test_promoted_state_allows_gate_mutation(self, tmp_path):
        """promoted→quarantined edge: promoted is NOT terminal so gate field is mutable."""
        _seed_ticket(tmp_path, FP_A, state="promoted",
                     gates={"tests_pass": True, "ci_pass": True, "user_approved": True})
        # Should NOT raise — promoted is no longer a terminal state
        out = set_gate_field(tmp_path, FP_A, "tests_pass", False)
        assert out["promotion_gate"]["tests_pass"] is False

    def test_terminal_state_rejected_blocks_gate(self, tmp_path):
        _seed_ticket(tmp_path, FP_A, state="rejected")
        with pytest.raises(PromotionError, match="terminal"):
            set_gate_field(tmp_path, FP_A, "tests_pass", True)


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

    def test_quarantined_blocks_forward_transitions(self, tmp_path):
        """quarantined can only go to promoted or rejected — not candidate/etc."""
        _seed_ticket(tmp_path, FP_A, state="quarantined",
                     gates={"tests_pass": True, "ci_pass": True, "user_approved": True})
        with pytest.raises(PromotionError, match="quarantined -> candidate"):
            transition(tmp_path, FP_A, "candidate")

    def test_promoted_to_quarantined_transition(self, tmp_path):
        """promoted -> quarantined is a valid FSM edge."""
        _seed_ticket(tmp_path, FP_A, state="promoted",
                     gates={"tests_pass": True, "ci_pass": True, "user_approved": True})
        out = transition(tmp_path, FP_A, "quarantined")
        assert out["state"] == "quarantined"

    def test_transition_result_still_schema_valid(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        out = transition(tmp_path, FP_A, "accepted")
        from _improvement import validate_ticket
        validate_ticket(out)

    def test_corrupt_ticket_raises_promotion_error(self, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / f"{FP_A}.json").write_text("{not json")
        with pytest.raises(PromotionError, match="corrupt"):
            transition(tmp_path, FP_A, "accepted")


# ---------------------------------------------------------------------------
# Orchestrator CLI shims
# ---------------------------------------------------------------------------

import orchestrator  # type: ignore[import-not-found]  # noqa: E402


def _run(argv: list[str]) -> int:
    return orchestrator.main(argv)


def _make_ledger(tmp_path: Path, fp: str, state: str = "candidate") -> tuple[Path, Path]:
    """Seed a ticket and return (ledger_dir, repo_root).

    HOME is NOT monkeypatched here — callers must do that.
    """
    slug = str(tmp_path / "repo").replace("/", "-")
    ledger = tmp_path / "home" / ".claude" / "projects" / slug / "improvements"
    _seed_ticket(ledger, fp, state=state)
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    return ledger, repo_root


class TestImprovementsListPromotableCLI:
    """--promotable flag filters to tickets meeting promotion thresholds."""

    def test_promotable_flag_filters_correctly(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        slug = str(tmp_path / "repo").replace("/", "-")
        ledger = tmp_path / "home" / ".claude" / "projects" / slug / "improvements"
        ledger.mkdir(parents=True, exist_ok=True)

        # Above threshold: reviewer-finding requires distinct_runs >= 2
        above = {
            "schema_version": 1,
            "fingerprint": FP_A,
            "state": "candidate",
            "pattern": "above",
            "source": "reviewer-finding",
            "candidate_asset": None,
            "occurrences": 2,
            "distinct_runs": 2,
            "first_seen": "2026-06-10T08:00:39Z",
            "last_seen": "2026-06-12T23:06:46Z",
            "plugin_version": "0",
            "repo_fingerprint": "abc123",
            "evidence": [{"run_id": "r1", "snippet": "s"}, {"run_id": "r2", "snippet": "s2"}],
            "promotion_gate": {"tests_pass": None, "ci_pass": None, "user_approved": None},
        }
        # Below threshold: distinct_runs = 1
        below = {**above, "fingerprint": FP_B, "pattern": "below", "distinct_runs": 1,
                 "occurrences": 1, "evidence": [{"run_id": "r1", "snippet": "s"}]}

        (ledger / f"{FP_A}.json").write_text(json.dumps(above))
        (ledger / f"{FP_B}.json").write_text(json.dumps(below))

        repo_root = tmp_path / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)

        rc = _run(["improvements-list", "--repo-root", str(repo_root),
                   "--promotable", "--json"])
        assert rc == 0
        lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln]
        assert len(lines) == 1
        ticket = json.loads(lines[0])
        assert ticket["fingerprint"] == FP_A


class TestImprovementsListCLI:
    def test_list_empty_ledger(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        repo = tmp_path / "repo"
        repo.mkdir(parents=True)
        rc = _run(["improvements-list", "--repo-root", str(repo)])
        assert rc == 0

    def test_list_shows_ticket(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        _ledger_dir, repo_root = _make_ledger(tmp_path, FP_A)
        rc = _run(["improvements-list", "--repo-root", str(repo_root)])
        assert rc == 0
        out = capsys.readouterr().out
        assert FP_A[:8] in out

    def test_list_json_flag(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        _ledger_dir, repo_root = _make_ledger(tmp_path, FP_A)
        rc = _run(["improvements-list", "--repo-root", str(repo_root), "--json"])
        assert rc == 0
        lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln]
        assert len(lines) == 1
        ticket = json.loads(lines[0])
        assert ticket["fingerprint"] == FP_A

    def test_list_state_filter(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        _ledger_dir, repo_root = _make_ledger(tmp_path, FP_A, state="accepted")
        _seed_ticket(_ledger_dir, FP_B, state="candidate")
        rc = _run(["improvements-list", "--repo-root", str(repo_root),
                   "--state", "accepted", "--json"])
        assert rc == 0
        lines = [ln for ln in capsys.readouterr().out.strip().splitlines() if ln]
        assert len(lines) == 1
        assert json.loads(lines[0])["state"] == "accepted"


class TestImprovementsGateCLI:
    def test_sets_gate_field(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        _ledger_dir, repo_root = _make_ledger(tmp_path, FP_A)
        rc = _run(["improvements-gate", "--repo-root", str(repo_root),
                   FP_A[:8], "--field", "tests_pass", "--value", "true"])
        assert rc == 0
        out = capsys.readouterr().out
        gate = json.loads(out)
        assert gate["tests_pass"] is True

    def test_unknown_field_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        _ledger_dir, repo_root = _make_ledger(tmp_path, FP_A)
        with pytest.raises(SystemExit) as exc_info:
            _run(["improvements-gate", "--repo-root", str(repo_root),
                  FP_A[:8], "--field", "vibes", "--value", "true"])
        assert exc_info.value.code != 0

    def test_ambiguous_prefix_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        _ledger_dir, repo_root = _make_ledger(tmp_path, FP_A)
        _seed_ticket(_ledger_dir, FP_B)
        rc = _run(["improvements-gate", "--repo-root", str(repo_root),
                   "a", "--field", "tests_pass", "--value", "true"])
        assert rc == 1


class TestImprovementsSetStateCLI:
    def test_valid_transition(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        _ledger_dir, repo_root = _make_ledger(tmp_path, FP_A)
        rc = _run(["improvements-set-state", "--repo-root", str(repo_root),
                   FP_A[:8], "accepted"])
        assert rc == 0
        assert "accepted" in capsys.readouterr().out

    def test_illegal_transition_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        _ledger_dir, repo_root = _make_ledger(tmp_path, FP_A)
        rc = _run(["improvements-set-state", "--repo-root", str(repo_root),
                   FP_A[:8], "promoted"])
        assert rc == 1

    def test_unknown_state_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        _ledger_dir, repo_root = _make_ledger(tmp_path, FP_A)
        rc = _run(["improvements-set-state", "--repo-root", str(repo_root),
                   FP_A[:8], "nope"])
        assert rc == 1


# ---------------------------------------------------------------------------
# FIX #2 — audit timestamp on gate write
# ---------------------------------------------------------------------------

class TestGateAuditTimestamp:
    def test_true_records_parseable_iso_timestamp(self, tmp_path):
        """Setting a gate field to True records a parseable UTC ISO-8601 *_at timestamp."""
        _seed_ticket(tmp_path, FP_A)
        before = datetime.now(timezone.utc)
        out = set_gate_field(tmp_path, FP_A, "user_approved", True)
        after = datetime.now(timezone.utc)

        ts_str = out["promotion_gate"].get("user_approved_at")
        assert ts_str is not None, "user_approved_at should be set when value=True"
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        assert before <= ts <= after

    def test_at_field_persisted_to_disk(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        set_gate_field(tmp_path, FP_A, "ci_pass", True)
        on_disk = json.loads((tmp_path / f"{FP_A}.json").read_text())
        assert "ci_pass_at" in on_disk["promotion_gate"]
        datetime.fromisoformat(on_disk["promotion_gate"]["ci_pass_at"].replace("Z", "+00:00"))

    def test_false_does_not_record_at_timestamp(self, tmp_path):
        """Setting a gate field to False must NOT record a *_at field."""
        _seed_ticket(tmp_path, FP_A)
        out = set_gate_field(tmp_path, FP_A, "tests_pass", False)
        assert "tests_pass_at" not in out["promotion_gate"]

    def test_at_field_schema_valid_after_set(self, tmp_path):
        """The ticket with *_at field still passes schema validation."""
        _seed_ticket(tmp_path, FP_A)
        out = set_gate_field(tmp_path, FP_A, "tests_pass", True)
        from _improvement import validate_ticket
        validate_ticket(out)

    def test_all_three_gate_fields_get_at_timestamps(self, tmp_path):
        _seed_ticket(tmp_path, FP_A)
        for field in GATE_FIELDS:
            set_gate_field(tmp_path, FP_A, field, True)
        on_disk = json.loads((tmp_path / f"{FP_A}.json").read_text())
        gate = on_disk["promotion_gate"]
        for field in GATE_FIELDS:
            assert f"{field}_at" in gate, f"missing {field}_at"


# ---------------------------------------------------------------------------
# FIX #4 — lock teardown on exception (regression test; lock is already correct)
# ---------------------------------------------------------------------------

class TestLockTeardownOnException:
    def test_lock_released_when_mutate_raises(self, tmp_path):
        """Exception inside mutate must not leave a stale flock; LOCK_NB acquire proves it."""
        import fcntl

        _seed_ticket(tmp_path, FP_A)

        def _raiser(ticket: Ticket) -> Ticket:
            raise RuntimeError("injected failure")

        from _promotion import _locked_update

        with pytest.raises(RuntimeError, match="injected failure"):
            _locked_update(tmp_path, FP_A, _raiser)

        lock_path = tmp_path / f"{FP_A}.json.lock"
        with lock_path.open("r+") as fd:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# FIX #5 — pre-mutate schema validation
# ---------------------------------------------------------------------------

class TestPreMutateSchemaValidation:
    def test_invalid_ticket_raises_before_mutation(self, tmp_path):
        """Schema-invalid ticket on disk raises a clear PromotionError naming the ticket;
        mutate body must NOT be called."""
        bad = {
            "schema_version": 1, "fingerprint": FP_A, "state": "candidate",
            "pattern": "x", "source": "insight", "candidate_asset": "hook",
            "occurrences": 1, "distinct_runs": 1,
            "first_seen": "2026-06-10T00:00:00Z", "last_seen": "2026-06-10T00:00:00Z",
            "plugin_version": "0", "repo_fingerprint": "abc",
            "evidence": [{"run_id": "r1", "snippet": "s"}],
            "promotion_gate": {"tests_pass": None, "ci_pass": None, "user_approved": None},
            "BOGUS_EXTRA_FIELD": True,
        }
        (tmp_path / f"{FP_A}.json").write_text(json.dumps(bad))

        mutated: list[bool] = []

        def tracking_mutate(t: Ticket) -> Ticket:
            mutated.append(True)
            return t

        from _promotion import _locked_update
        with pytest.raises(PromotionError, match="invalid before mutation") as exc_info:
            _locked_update(tmp_path, FP_A, tracking_mutate)

        assert mutated == [], "mutate body must NOT be called when pre-validation fails"
        assert FP_A in str(exc_info.value) or "invalid before" in str(exc_info.value)
