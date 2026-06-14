"""Tests for scripts/_escalation.py — escalation-record identity + ledger I/O.

All library-function tests inject ``now`` and ``retrieved_date``; no wall-clock
dependency.  FakeFetcher mirrors the pattern from test_enrich_fetch.py.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _escalation  # noqa: E402
from _escalation import (  # noqa: E402
    Observation,
    bump_or_create,
    compute_fingerprint,
    drive_enrich,
    ledger_dir,
    validate_escalation,
    _load_record,
    _record_enrichment,  # noqa: F401 (referenced by name in source-check test)
)

NOW = datetime(2026, 6, 14, tzinfo=timezone.utc)
RETRIEVED = "2026-06-14"

FP_64 = "a" * 64


# ---------------------------------------------------------------------------
# FakeFetcher (mirrors test_enrich_fetch.py pattern)
# ---------------------------------------------------------------------------


class FakeFetcher:
    """Deterministic stand-in for the real MCP fetcher."""

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


def _community_hit(
    snippet: str = "Community tip about cleanup.",
    url: str = "https://reddit.com/r/reactjs/123",
    claim: str = "Community claim.",
) -> dict:
    return {"claim": claim, "source_url": url, "snippet": snippet}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_record(fp: str = FP_64) -> dict:
    """Return a schema-valid escalation record dict."""
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


def _obs(
    problem_class: str = "unknown-library",
    query: str = "react useEffect cleanup",
    approach: str = "_enrich_gate.evaluate",
    outcome: str = "reject: single-source",
    run_id: str = "r1",
    snippet: str = "needed cleanup semantics",
) -> Observation:
    return Observation(
        problem_class=problem_class,
        suggested_enrich_query=query,
        approach=approach,
        outcome=outcome,
        run_id=run_id,
        snippet=snippet,
    )


# ===========================================================================
# 1. Schema validation
# ===========================================================================


class TestSchemaValidation:
    def test_valid_passes(self) -> None:
        validate_escalation(_valid_record())

    def test_extra_property_root_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["bogus"] = True
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_extra_property_in_tried_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["tried"] = [{"approach": "x", "unknown_key": True}]
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_extra_property_in_evidence_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["evidence"] = [{"run_id": "r1", "snippet": "s", "unknown_key": True}]
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_extra_property_in_enrichment_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["state"] = "enriched"
        r["enrichment"] = {
            "query": "q",
            "enriched_at": "2026-06-14T00:00:00Z",
            "counts": {"admitted": 1, "rejected": 0, "written": 1, "unchanged": 0},
            "bogus": True,
        }
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_bad_state_enum_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["state"] = "nope"
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_bad_problem_class_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["problem_class"] = "alien-class"
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_short_fingerprint_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["fingerprint"] = "abc"
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_empty_suggested_enrich_query_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["suggested_enrich_query"] = ""
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_empty_tried_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["tried"] = []
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_empty_evidence_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["evidence"] = []
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_schema_version_not_1_rejected(self) -> None:
        import jsonschema
        r = _valid_record()
        r["schema_version"] = 2
        with pytest.raises(jsonschema.ValidationError):
            validate_escalation(r)

    def test_valid_enrichment_block_passes(self) -> None:
        r = _valid_record()
        r["state"] = "enriched"
        r["enrichment"] = {
            "query": "react useEffect cleanup",
            "enriched_at": "2026-06-14T00:00:00Z",
            "retrieved_date": RETRIEVED,
            "counts": {"admitted": 1, "rejected": 0, "written": 1, "unchanged": 0},
        }
        validate_escalation(r)


# ===========================================================================
# 2. Fingerprint / dedup
# ===========================================================================


class TestFingerprint:
    def test_deterministic_64_hex(self) -> None:
        fp = compute_fingerprint("unknown-library", "react useEffect cleanup")
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_query_case_whitespace_variants_collide(self) -> None:
        a = compute_fingerprint("unknown-library", "react useEffect cleanup")
        b = compute_fingerprint("unknown-library", "React  useEffect  Cleanup ")
        c = compute_fingerprint("unknown-library", "  react useeffect cleanup  ")
        assert a == b == c

    def test_different_problem_class_different_fp(self) -> None:
        a = compute_fingerprint("unknown-library", "react useEffect cleanup")
        b = compute_fingerprint("doom-loop", "react useEffect cleanup")
        assert a != b

    def test_two_run_ids_same_query_one_file(self, tmp_path: Path) -> None:
        obs1 = _obs(run_id="r1", snippet="s1")
        obs2 = _obs(run_id="r2", snippet="s2")
        bump_or_create(tmp_path, obs1, repo_root=tmp_path, now=NOW, dry_run=False)
        t = bump_or_create(tmp_path, obs2, repo_root=tmp_path, now=NOW, dry_run=False)
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert t["distinct_runs"] == 2


# ===========================================================================
# 3. RMW — bump_or_create
# ===========================================================================


class TestBumpOrCreate:
    def test_creates_open_state(self, tmp_path: Path) -> None:
        t = bump_or_create(tmp_path, _obs(), repo_root=tmp_path, now=NOW, dry_run=False)
        assert t["state"] == "open"

    def test_dedups_evidence_on_run_id_snippet(self, tmp_path: Path) -> None:
        obs = _obs(run_id="r1", snippet="s")
        bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)
        t = bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)
        assert t["occurrences"] == 1

    def test_accumulates_distinct_runs(self, tmp_path: Path) -> None:
        bump_or_create(tmp_path, _obs(run_id="r1", snippet="s1"),
                       repo_root=tmp_path, now=NOW, dry_run=False)
        t = bump_or_create(tmp_path, _obs(run_id="r2", snippet="s2"),
                           repo_root=tmp_path, now=NOW, dry_run=False)
        assert t["distinct_runs"] == 2
        assert t["occurrences"] == 2

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        bump_or_create(tmp_path, _obs(), repo_root=tmp_path, now=NOW, dry_run=True)
        assert list(tmp_path.glob("*.json")) == []

    def test_byte_stability(self, tmp_path: Path) -> None:
        """Two bumps with identical NOW produce byte-identical files."""
        obs1 = _obs(run_id="r1", snippet="s1")
        bump_or_create(tmp_path, obs1, repo_root=tmp_path, now=NOW, dry_run=False)
        fp = compute_fingerprint(obs1.problem_class, obs1.suggested_enrich_query)
        bytes1 = (tmp_path / f"{fp}.json").read_bytes()

        # Write a second record with a different fingerprint so we can re-check first
        obs2 = _obs(run_id="r2", snippet="s2", problem_class="doom-loop")
        bump_or_create(tmp_path, obs2, repo_root=tmp_path, now=NOW, dry_run=False)

        # First file must not have changed
        bytes2 = (tmp_path / f"{fp}.json").read_bytes()
        assert bytes1 == bytes2

    def test_ledger_dir_home_store_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        from _improvement import project_slug
        root = tmp_path / "repo"
        root.mkdir()
        led = ledger_dir(root, None)
        expected = tmp_path / ".claude" / "projects" / project_slug(root) / "escalations"
        assert led == expected

    def test_corrupt_record_reseeds(self, tmp_path: Path) -> None:
        obs = _obs()
        fp = compute_fingerprint(obs.problem_class, obs.suggested_enrich_query)
        (tmp_path / f"{fp}.json").write_text("{not valid json")
        t = bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)
        assert t["occurrences"] == 1 and t["distinct_runs"] == 1
        validate_escalation(t)

    def test_bumped_record_is_schema_valid(self, tmp_path: Path) -> None:
        t = bump_or_create(tmp_path, _obs(), repo_root=tmp_path, now=NOW, dry_run=False)
        validate_escalation(t)


# ===========================================================================
# 4. ACCEPTANCE — worked record drives enrich admitted page
# ===========================================================================


def test_worked_record_drives_enrich_admitted_page(tmp_path: Path) -> None:
    """ACCEPTANCE: bump → drive_enrich → state=='enriched' + enrichment block + page."""
    ledger = tmp_path / "ledger"
    ledger.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()

    obs = _obs(
        problem_class="unknown-library",
        query="react useEffect cleanup",
    )
    bump_or_create(ledger, obs, repo_root=tmp_path, now=NOW, dry_run=False)
    fp = compute_fingerprint(obs.problem_class, obs.suggested_enrich_query)

    fetcher = FakeFetcher({"official": [_official_hit()]})
    counts = drive_enrich(
        ledger, fp, fetcher, vault,
        retrieved_date=RETRIEVED, now=NOW,
    )

    assert counts["admitted"] == 1
    assert counts["written"] == 1

    pages = list((vault / "enrichment").glob("enrich-*.md"))
    assert len(pages) == 1

    record = _load_record(ledger / f"{fp}.json")
    assert record is not None
    assert record["state"] == "enriched"
    assert record["enrichment"]["counts"] == counts


# ===========================================================================
# 5. Seam variants
# ===========================================================================


class TestSeamVariants:
    def test_community_single_source_rejected_state_still_enriched(
        self, tmp_path: Path
    ) -> None:
        """Community single-source → rejected==1, zero pages, state still 'enriched'."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        vault = tmp_path / "vault"
        vault.mkdir()

        obs = _obs()
        bump_or_create(ledger, obs, repo_root=tmp_path, now=NOW, dry_run=False)
        fp = compute_fingerprint(obs.problem_class, obs.suggested_enrich_query)

        fetcher = FakeFetcher({"community": [_community_hit()]})
        counts = drive_enrich(
            ledger, fp, fetcher, vault,
            retrieved_date=RETRIEVED, now=NOW,
        )
        assert counts["rejected"] == 1
        assert counts["admitted"] == 0
        pages = list((vault / "enrichment").glob("enrich-*.md")) if (vault / "enrichment").exists() else []
        assert pages == []

        record = _load_record(ledger / f"{fp}.json")
        assert record is not None
        assert record["state"] == "enriched"

    def test_dry_run_drive_enrich_no_files(self, tmp_path: Path) -> None:
        """dry_run drive_enrich → counts populated, no .md files, record not written."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        vault = tmp_path / "vault"
        vault.mkdir()

        obs = _obs()
        bump_or_create(ledger, obs, repo_root=tmp_path, now=NOW, dry_run=False)
        fp = compute_fingerprint(obs.problem_class, obs.suggested_enrich_query)

        fetcher = FakeFetcher({"official": [_official_hit()]})
        counts = drive_enrich(
            ledger, fp, fetcher, vault,
            retrieved_date=RETRIEVED, now=NOW, dry_run=True,
        )
        assert counts["admitted"] == 1

        pages = list((vault / "enrichment").glob("enrich-*.md")) if (vault / "enrichment").exists() else []
        assert pages == []

        record = _load_record(ledger / f"{fp}.json")
        assert record is not None
        assert record["state"] == "open", "dry_run must not mutate the record"

    def test_rerun_drive_enrich_same_date_unchanged(self, tmp_path: Path) -> None:
        """Rerun drive_enrich same date → unchanged==1 and page bytes identical."""
        ledger = tmp_path / "ledger"
        ledger.mkdir()
        vault = tmp_path / "vault"
        vault.mkdir()

        obs = _obs()
        bump_or_create(ledger, obs, repo_root=tmp_path, now=NOW, dry_run=False)
        fp = compute_fingerprint(obs.problem_class, obs.suggested_enrich_query)

        fetcher = FakeFetcher({"official": [_official_hit(snippet="Stable snippet.")]})
        drive_enrich(ledger, fp, fetcher, vault, retrieved_date=RETRIEVED, now=NOW)

        # Re-seed for second drive (bump to re-open state for testing)
        # Actually we just run again — state is already enriched, drive_enrich
        # re-runs persist which returns unchanged on same content.
        pages = list((vault / "enrichment").glob("enrich-*.md"))
        bytes1 = pages[0].read_bytes()

        counts2 = drive_enrich(
            ledger, fp, fetcher, vault, retrieved_date=RETRIEVED, now=NOW
        )
        assert counts2["unchanged"] == 1
        assert pages[0].read_bytes() == bytes1


# ===========================================================================
# 6. Byte-stability: no datetime.now / date.today in library functions
# ===========================================================================


class TestByteStabilitySourceCheck:
    def test_library_functions_have_no_datetime_now(self) -> None:
        # Check the library functions individually (cmd_* handlers are allowed)
        for fn_name in ("bump_or_create", "_record_enrichment", "drive_enrich"):
            fn = getattr(_escalation, fn_name, None)
            if fn is None:
                continue
            fn_src = inspect.getsource(fn)
            assert "datetime.now" not in fn_src, (
                f"{fn_name} must not call datetime.now"
            )
            assert "date.today" not in fn_src, (
                f"{fn_name} must not call date.today"
            )
