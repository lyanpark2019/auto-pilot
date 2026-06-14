"""Guard tests for _escalation.py FSM + whitespace-query + schema coupling.

RED-style: each test verifies a guard REJECTS bad input and ACCEPTS good input.
FakeFetcher and _official_hit are local copies (test_escalation.py is ≤500 lines
and cannot absorb these; shared-import would create implicit coupling).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _escalation  # noqa: E402
from _escalation import (  # noqa: E402
    Observation,
    bump_or_create,
    compute_fingerprint,
    drive_enrich,
    validate_escalation,
    _load_record,
)

NOW = datetime(2026, 6, 14, tzinfo=timezone.utc)
RETRIEVED = "2026-06-14"
FP_64 = "a" * 64


# ---------------------------------------------------------------------------
# FakeFetcher (local copy — keeps test_escalation.py under 500 lines)
# ---------------------------------------------------------------------------


class FakeFetcher:
    def __init__(self, hits_by_tier: dict[str, list[dict]]) -> None:
        self._hits = hits_by_tier

    def fetch(self, query: str, tier: str) -> list[dict]:
        return self._hits.get(tier, [])


def _official_hit(
    snippet: str = "Official snippet for react useEffect cleanup.",
    url: str = "https://react.dev/reference/react/useEffect",
    claim: str = "useEffect cleanup runs before the next effect.",
) -> dict:
    return {"claim": claim, "source_url": url, "snippet": snippet}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_open_record(fp: str = FP_64) -> dict:
    return {
        "schema_version": 1,
        "fingerprint": fp,
        "state": "open",
        "problem_class": "unknown-library",
        "tried": [{"approach": "_enrich_gate.evaluate", "outcome": "reject: single-source"}],
        "evidence": [{"run_id": "r1", "snippet": "needed cleanup semantics"}],
        "suggested_enrich_query": "react useEffect cleanup",
        "first_seen": "2026-06-14T00:00:00Z",
        "last_seen": "2026-06-14T00:00:00Z",
        "occurrences": 1,
        "distinct_runs": 1,
        "plugin_version": "0.8.9",
        "repo_fingerprint": "abc123",
    }


def _write_record(ledger: Path, record: dict) -> Path:
    path = ledger / f"{record['fingerprint']}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def _obs(
    query: str = "react useEffect cleanup",
    run_id: str = "r1",
    snippet: str = "needed cleanup semantics",
) -> Observation:
    return Observation(
        problem_class="unknown-library",
        suggested_enrich_query=query,
        approach="_enrich_gate.evaluate",
        outcome="reject: single-source",
        run_id=run_id,
        snippet=snippet,
    )


# ===========================================================================
# 1. FSM guard: drive_enrich on terminal states
# ===========================================================================


class TestFSMGuard:
    def test_resolved_record_drive_enrich_raises(self, tmp_path: Path) -> None:
        """drive_enrich on a resolved record raises ValueError; disk unchanged."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        vault = tmp_path / "vault"
        vault.mkdir()

        record = _valid_open_record()
        record["state"] = "resolved"
        _write_record(ledger, record)

        fetcher = FakeFetcher({"official": [_official_hit()]})
        with pytest.raises(ValueError, match="illegal escalation transition"):
            drive_enrich(
                ledger, FP_64, fetcher, vault,
                retrieved_date=RETRIEVED, now=NOW,
            )

        on_disk = _load_record(ledger / f"{FP_64}.json")
        assert on_disk is not None
        assert on_disk["state"] == "resolved", "on-disk state must not change"
        pages = list((vault / "enrichment").glob("enrich-*.md")) if (vault / "enrichment").exists() else []
        assert pages == [], "no pages written on FSM rejection"

    def test_abandoned_record_drive_enrich_raises(self, tmp_path: Path) -> None:
        """drive_enrich on an abandoned record raises ValueError; disk unchanged."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        vault = tmp_path / "vault"
        vault.mkdir()

        record = _valid_open_record()
        record["state"] = "abandoned"
        _write_record(ledger, record)

        fetcher = FakeFetcher({"official": [_official_hit()]})
        with pytest.raises(ValueError, match="illegal escalation transition"):
            drive_enrich(
                ledger, FP_64, fetcher, vault,
                retrieved_date=RETRIEVED, now=NOW,
            )

        on_disk = _load_record(ledger / f"{FP_64}.json")
        assert on_disk is not None
        assert on_disk["state"] == "abandoned"

    def test_open_record_drive_enrich_succeeds(self, tmp_path: Path) -> None:
        """POSITIVE: open → drive_enrich → state 'enriched'."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        vault = tmp_path / "vault"
        vault.mkdir()

        obs = _obs()
        bump_or_create(ledger, obs, repo_root=tmp_path, now=NOW, dry_run=False)
        fp = compute_fingerprint(obs.problem_class, obs.suggested_enrich_query)

        fetcher = FakeFetcher({"official": [_official_hit()]})
        drive_enrich(ledger, fp, fetcher, vault, retrieved_date=RETRIEVED, now=NOW)

        on_disk = _load_record(ledger / f"{fp}.json")
        assert on_disk is not None
        assert on_disk["state"] == "enriched"

    def test_enriched_record_drive_enrich_idempotent(self, tmp_path: Path) -> None:
        """POSITIVE: enriched → drive_enrich again → stays 'enriched' (idempotent refresh)."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        vault = tmp_path / "vault"
        vault.mkdir()

        obs = _obs()
        bump_or_create(ledger, obs, repo_root=tmp_path, now=NOW, dry_run=False)
        fp = compute_fingerprint(obs.problem_class, obs.suggested_enrich_query)

        fetcher = FakeFetcher({"official": [_official_hit()]})
        drive_enrich(ledger, fp, fetcher, vault, retrieved_date=RETRIEVED, now=NOW)
        drive_enrich(ledger, fp, fetcher, vault, retrieved_date=RETRIEVED, now=NOW)

        on_disk = _load_record(ledger / f"{fp}.json")
        assert on_disk is not None
        assert on_disk["state"] == "enriched"


# ===========================================================================
# 2. CLI FSM: cmd_escalation_enrich on a resolved record → rc1
# ===========================================================================


class TestCLIFSMGuard:
    def test_cmd_escalation_enrich_resolved_rc1(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """cmd_escalation_enrich on a resolved record → rc=1, stderr mentions transition."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()

        record = _valid_open_record()
        record["state"] = "resolved"
        _write_record(ledger, record)

        class Args:
            prefix = FP_64[:8]
            counts = '{"admitted":1,"rejected":0,"written":1,"unchanged":0}'
            query = None
            retrieved_date = RETRIEVED
            repo_root = str(tmp_path)
            vault = None
            dry_run = False

        import unittest.mock as mock
        with mock.patch.object(_escalation, "ledger_dir", return_value=ledger):
            rc = _escalation.cmd_escalation_enrich(Args())

        assert rc == 1
        captured = capsys.readouterr()
        assert "illegal escalation transition" in captured.err

        on_disk = _load_record(ledger / f"{FP_64}.json")
        assert on_disk is not None
        assert on_disk["state"] == "resolved"

    def test_cmd_escalation_enrich_resolved_dry_run_rc1(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """cmd_escalation_enrich dry_run on resolved → rc=1, stderr mentions transition."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()

        record = _valid_open_record()
        record["state"] = "resolved"
        _write_record(ledger, record)

        class Args:
            prefix = FP_64[:8]
            counts = '{"admitted":1,"rejected":0,"written":1,"unchanged":0}'
            query = None
            retrieved_date = RETRIEVED
            repo_root = str(tmp_path)
            vault = None
            dry_run = True

        import unittest.mock as mock
        with mock.patch.object(_escalation, "ledger_dir", return_value=ledger):
            rc = _escalation.cmd_escalation_enrich(Args())

        assert rc == 1
        captured = capsys.readouterr()
        assert "illegal escalation transition" in captured.err


# ===========================================================================
# 3. Whitespace-only query rejection in bump_or_create
# ===========================================================================


class TestWhitespaceQueryGuard:
    def test_spaces_only_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="non-whitespace"):
            bump_or_create(tmp_path, _obs(query="   "), repo_root=tmp_path, now=NOW, dry_run=False)

    def test_tab_newline_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="non-whitespace"):
            bump_or_create(tmp_path, _obs(query="\t\n"), repo_root=tmp_path, now=NOW, dry_run=False)

    def test_nonempty_query_succeeds(self, tmp_path: Path) -> None:
        record = bump_or_create(tmp_path, _obs(query="x"), repo_root=tmp_path, now=NOW, dry_run=False)
        assert record["suggested_enrich_query"] == "x"

    def test_spaces_only_dry_run_raises(self, tmp_path: Path) -> None:
        """Whitespace guard fires on dry_run path too (guard is before the branch)."""
        with pytest.raises(ValueError, match="non-whitespace"):
            bump_or_create(tmp_path, _obs(query="   "), repo_root=tmp_path, now=NOW, dry_run=True)


# ===========================================================================
# 4. Schema coupling: state=="enriched" requires enrichment block
# ===========================================================================


class TestSchemaCoupling:
    def test_enriched_state_without_enrichment_block_fails(self) -> None:
        """state='enriched' without enrichment block → ValidationError."""
        record = _valid_open_record()
        record["state"] = "enriched"
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(record)

    def test_enriched_state_with_enrichment_block_passes(self) -> None:
        """POSITIVE: state='enriched' with valid enrichment block → passes."""
        record = _valid_open_record()
        record["state"] = "enriched"
        record["enrichment"] = {
            "query": "react useEffect cleanup",
            "enriched_at": "2026-06-14T00:00:00Z",
            "retrieved_date": RETRIEVED,
            "counts": {"admitted": 1, "rejected": 0, "written": 1, "unchanged": 0},
        }
        validate_escalation(record)

    def test_open_record_without_enrichment_passes(self) -> None:
        """POSITIVE: open record with no enrichment block → passes."""
        record = _valid_open_record()
        assert "enrichment" not in record
        validate_escalation(record)

    def test_resolved_record_without_enrichment_passes(self) -> None:
        """POSITIVE: resolved record without enrichment block still valid."""
        record = _valid_open_record()
        record["state"] = "resolved"
        validate_escalation(record)

    def test_abandoned_record_without_enrichment_passes(self) -> None:
        """POSITIVE: abandoned record without enrichment block still valid."""
        record = _valid_open_record()
        record["state"] = "abandoned"
        validate_escalation(record)
