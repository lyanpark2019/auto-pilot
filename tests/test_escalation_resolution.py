"""Tests for _escalation.record_resolution writer and cmd_escalation_resolve CLI.

Mirrors test_escalation_guards.py structure.
GREEN paths: enriched→resolved, enriched→abandoned, open→abandoned.
RED paths (resurrection guard): resolved→abandoned, resolved→resolved,
  abandoned→resolved, abandoned→abandoned, resolved→resolved (same-state re-stamp),
  invalid new_state.
Concurrency: adversarial mixed resolved+abandoned fan-out — exactly one wins.
"""
from __future__ import annotations

import concurrent.futures as cf
import inspect
import json
import sys
import unittest.mock as mock
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _escalation  # noqa: E402
from _escalation import (  # noqa: E402
    Observation,
    bump_or_create,
    compute_fingerprint,
    record_resolution,
    validate_escalation,
    _load_record,
    _record_enrichment,
)

NOW = datetime(2026, 6, 15, tzinfo=timezone.utc)
FP_64 = "b" * 64
RETRIEVED = "2026-06-15"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_open_record(fp: str = FP_64) -> dict:
    return {
        "schema_version": 1,
        "fingerprint": fp,
        "state": "open",
        "problem_class": "doom-loop",
        "tried": [{"approach": "cmd_pivot_check", "outcome": "repeat-3"}],
        "evidence": [{"run_id": "r1", "snippet": "same finding hash x3"}],
        "suggested_enrich_query": "doom loop resolution strategies",
        "first_seen": "2026-06-15T00:00:00Z",
        "last_seen": "2026-06-15T00:00:00Z",
        "occurrences": 1,
        "distinct_runs": 1,
        "plugin_version": "0.9.0",
        "repo_fingerprint": "abc123",
    }


def _valid_enriched_record(fp: str = FP_64) -> dict:
    record = _valid_open_record(fp)
    record["state"] = "enriched"
    record["enrichment"] = {
        "query": "doom loop resolution strategies",
        "enriched_at": "2026-06-15T00:00:00Z",
        "retrieved_date": RETRIEVED,
        "counts": {"admitted": 1, "rejected": 0, "written": 1, "unchanged": 0},
    }
    return record


def _write_record(ledger: Path, record: dict) -> Path:
    path = ledger / f"{record['fingerprint']}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def _obs() -> Observation:
    return Observation(
        problem_class="doom-loop",
        suggested_enrich_query="doom loop resolution strategies",
        approach="cmd_pivot_check",
        outcome="repeat-3",
        run_id="r1",
        snippet="same finding hash x3",
    )


# ===========================================================================
# 1. GREEN: valid transitions produce schema-valid records with resolved_at
# ===========================================================================


class TestGreenPaths:
    def test_enriched_to_resolved(self) -> None:
        record = _valid_enriched_record()
        result = record_resolution(dict(record), "resolved", now=NOW)
        validate_escalation(result)
        assert result["state"] == "resolved"
        assert result["resolved_at"] == "2026-06-15T00:00:00Z"

    def test_enriched_to_abandoned(self) -> None:
        record = _valid_enriched_record()
        result = record_resolution(dict(record), "abandoned", now=NOW)
        validate_escalation(result)
        assert result["state"] == "abandoned"
        assert result["resolved_at"] == "2026-06-15T00:00:00Z"

    def test_open_to_abandoned(self) -> None:
        record = _valid_open_record()
        result = record_resolution(dict(record), "abandoned", now=NOW)
        validate_escalation(result)
        assert result["state"] == "abandoned"
        assert result["resolved_at"] == "2026-06-15T00:00:00Z"

    def test_resolved_at_matches_injected_now(self) -> None:
        now2 = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        record = _valid_enriched_record()
        result = record_resolution(dict(record), "resolved", now=now2)
        assert result["resolved_at"] == "2030-01-01T12:00:00Z"


# ===========================================================================
# 2. RED: resurrection guard — terminal records must not be re-transitioned
# ===========================================================================


class TestResurrectionGuard:
    def test_resolved_to_abandoned_raises(self) -> None:
        record = _valid_enriched_record()
        record["state"] = "resolved"
        record["resolved_at"] = "2026-06-15T00:00:00Z"
        with pytest.raises(ValueError, match="already terminal"):
            record_resolution(dict(record), "abandoned", now=NOW)

    def test_abandoned_to_resolved_raises(self) -> None:
        record = _valid_open_record()
        record["state"] = "abandoned"
        record["resolved_at"] = "2026-06-15T00:00:00Z"
        with pytest.raises(ValueError, match="already terminal"):
            record_resolution(dict(record), "resolved", now=NOW)

    def test_resolved_to_resolved_raises(self) -> None:
        """Same-state re-stamp on resolved must be blocked (no-resurrection invariant)."""
        record = _valid_enriched_record()
        record["state"] = "resolved"
        record["resolved_at"] = "2026-06-15T00:00:00Z"
        with pytest.raises(ValueError, match="already terminal"):
            record_resolution(dict(record), "resolved", now=NOW)

    def test_abandoned_to_abandoned_raises(self) -> None:
        """Same-state re-stamp on abandoned must be blocked."""
        record = _valid_open_record()
        record["state"] = "abandoned"
        record["resolved_at"] = "2026-06-15T00:00:00Z"
        with pytest.raises(ValueError, match="already terminal"):
            record_resolution(dict(record), "abandoned", now=NOW)

    def test_invalid_new_state_enriched_raises(self) -> None:
        record = _valid_open_record()
        with pytest.raises(ValueError, match="invalid resolution state"):
            record_resolution(dict(record), "enriched", now=NOW)

    def test_invalid_new_state_open_raises(self) -> None:
        record = _valid_open_record()
        with pytest.raises(ValueError, match="invalid resolution state"):
            record_resolution(dict(record), "open", now=NOW)

    def test_invalid_new_state_bogus_raises(self) -> None:
        record = _valid_open_record()
        with pytest.raises(ValueError, match="invalid resolution state"):
            record_resolution(dict(record), "bogus", now=NOW)


# ===========================================================================
# 3. resolved_at byte-stability: no datetime.now() in record_resolution
# ===========================================================================


class TestNowInjection:
    def test_no_datetime_now_in_record_resolution(self) -> None:
        """record_resolution must not call datetime.now() — now is injected."""
        src = inspect.getsource(record_resolution)
        assert "datetime.now" not in src, (
            "record_resolution must not call datetime.now() — now is a caller parameter"
        )

    def test_resolved_at_byte_stable_under_injected_now(self) -> None:
        fixed = datetime(2026, 6, 15, 8, 0, 0, tzinfo=timezone.utc)
        r1 = record_resolution(dict(_valid_enriched_record()), "resolved", now=fixed)
        r2 = record_resolution(dict(_valid_enriched_record()), "resolved", now=fixed)
        assert r1["resolved_at"] == r2["resolved_at"] == "2026-06-15T08:00:00Z"


# ===========================================================================
# 4. Concurrent cmd_escalation_resolve — no lost update under flock
# ===========================================================================


class TestConcurrentResolve:
    def test_parallel_resolve_no_lost_update(self, tmp_path: Path) -> None:
        """Adversarial: mixed resolved+abandoned fan-out — exactly one wins, rest rc2.

        This test is meaningful only with the terminal-state reject in
        record_resolution; without it all N would return rc0 (same-state refresh),
        the assert below would fail, and the flock proof would be vacuous.
        """
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        obs = _obs()
        bump_or_create(ledger, obs, repo_root=tmp_path, now=NOW, dry_run=False)
        fp = compute_fingerprint(obs.problem_class, obs.suggested_enrich_query)

        # Drive to enriched — required so resolved AND abandoned are both legal first moves.
        record_path = ledger / f"{fp}.json"
        record = _load_record(record_path)
        assert record is not None
        enriched = _record_enrichment(
            record, obs.suggested_enrich_query,
            {"admitted": 1, "rejected": 0, "written": 1, "unchanged": 0},
            now=NOW, retrieved_date=RETRIEVED,
        )
        import _contract  # noqa: PLC0415
        _contract.atomic_write_text(
            record_path, json.dumps(enriched, indent=2, sort_keys=True) + "\n"
        )

        def do_resolve(state: str) -> int:
            class Args:
                prefix = fp[:8]
                new_state = state
                repo_root = str(tmp_path)
                dry_run = False

            with mock.patch.object(_escalation, "ledger_dir", return_value=ledger):
                return _escalation.cmd_escalation_resolve(Args())

        # 3× "resolved" + 3× "abandoned" = 6 concurrent callers; winner is whichever
        # thread acquires the flock first; all subsequent callers must get rc2.
        targets = ["resolved"] * 3 + ["abandoned"] * 3
        with cf.ThreadPoolExecutor(max_workers=6) as ex:
            futs = [ex.submit(do_resolve, t) for t in targets]
            results = [f.result() for f in futs]

        # Exactly one winner (rc 0) — proves the flock serializes the RMW.
        assert results.count(0) == 1, (
            f"expected exactly 1 winner, got {results.count(0)}; results={results}"
        )
        # All losers must return rc2 (not silently succeed).
        for rc in results:
            if rc != 0:
                assert rc == 2, f"loser returned unexpected rc {rc}"

        # On-disk record is schema-valid and matches the winner's target state.
        on_disk = _load_record(record_path)
        assert on_disk is not None
        validate_escalation(on_disk)
        assert on_disk["state"] in {"resolved", "abandoned"}
        assert "resolved_at" in on_disk

        # The winner's resolved_at must not have been re-stamped by a subsequent loser.
        winner_rc0_idx = results.index(0)
        winner_state = targets[winner_rc0_idx]
        assert on_disk["state"] == winner_state, (
            f"on-disk state {on_disk['state']!r} != winner target {winner_state!r}"
        )


# ===========================================================================
# 5. CLI: cmd_escalation_resolve
# ===========================================================================


class TestCLIResolve:
    def test_rc0_on_valid_resolve(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        record = _valid_enriched_record()
        _write_record(ledger, record)

        class Args:
            prefix = FP_64[:8]
            new_state = "resolved"
            repo_root = str(tmp_path)
            dry_run = False

        with mock.patch.object(_escalation, "ledger_dir", return_value=ledger):
            rc = _escalation.cmd_escalation_resolve(Args())

        assert rc == 0
        on_disk = _load_record(ledger / f"{FP_64}.json")
        assert on_disk is not None
        assert on_disk["state"] == "resolved"
        assert "resolved_at" in on_disk

    def test_rc2_on_nonexistent_prefix(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        ledger = tmp_path / "ledger"
        ledger.mkdir()

        class Args:
            prefix = "deadbeef"
            new_state = "resolved"
            repo_root = str(tmp_path)
            dry_run = False

        with mock.patch.object(_escalation, "ledger_dir", return_value=ledger):
            rc = _escalation.cmd_escalation_resolve(Args())

        assert rc == 2
        captured = capsys.readouterr()
        assert "error" in captured.err

    def test_rc2_on_illegal_transition(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """resolved→abandoned is now caught by the terminal-state guard, not FSM."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        record = _valid_enriched_record()
        record["state"] = "resolved"
        record["resolved_at"] = "2026-06-15T00:00:00Z"
        _write_record(ledger, record)

        class Args:
            prefix = FP_64[:8]
            new_state = "abandoned"
            repo_root = str(tmp_path)
            dry_run = False

        with mock.patch.object(_escalation, "ledger_dir", return_value=ledger):
            rc = _escalation.cmd_escalation_resolve(Args())

        assert rc == 2
        captured = capsys.readouterr()
        assert "already terminal" in captured.err

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        record = _valid_enriched_record()
        _write_record(ledger, record)

        class Args:
            prefix = FP_64[:8]
            new_state = "resolved"
            repo_root = str(tmp_path)
            dry_run = True

        with mock.patch.object(_escalation, "ledger_dir", return_value=ledger):
            rc = _escalation.cmd_escalation_resolve(Args())

        assert rc == 0
        on_disk = _load_record(ledger / f"{FP_64}.json")
        assert on_disk is not None
        assert on_disk["state"] == "enriched", "dry_run must not persist the state change"

    def test_open_to_abandoned_via_cli(self, tmp_path: Path) -> None:
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        record = _valid_open_record()
        _write_record(ledger, record)

        class Args:
            prefix = FP_64[:8]
            new_state = "abandoned"
            repo_root = str(tmp_path)
            dry_run = False

        with mock.patch.object(_escalation, "ledger_dir", return_value=ledger):
            rc = _escalation.cmd_escalation_resolve(Args())

        assert rc == 0
        on_disk = _load_record(ledger / f"{FP_64}.json")
        assert on_disk is not None
        assert on_disk["state"] == "abandoned"

    def test_rc2_on_terminal_re_resolve(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """CLI: escalation-resolve on already-resolved record → rc2, stderr 'already terminal'."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        record = _valid_enriched_record()
        record["state"] = "resolved"
        record["resolved_at"] = "2026-06-15T00:00:00Z"
        _write_record(ledger, record)

        class Args:
            prefix = FP_64[:8]
            new_state = "resolved"
            repo_root = str(tmp_path)
            dry_run = False

        with mock.patch.object(_escalation, "ledger_dir", return_value=ledger):
            rc = _escalation.cmd_escalation_resolve(Args())

        assert rc == 2
        captured = capsys.readouterr()
        assert "already terminal" in captured.err
