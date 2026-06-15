"""Tests for scripts/measure_escalation.py — escalation-ledger measurement instrument.

Uses schema-valid record fixture dicts (validated via _escalation.validate_escalation)
and the real measure() — no mocking of ledger internals.  Exercises the full output
shape: by_state, by_problem_class, rate guards, enrich accounting, CLI smoke.
"""
from __future__ import annotations

import copy
import inspect
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import measure_escalation as me  # noqa: E402
from _escalation import validate_escalation  # noqa: E402

_FP_BASE = "a" * 64
_ALL_STATES = ("open", "enriched", "resolved", "abandoned")
_ALL_PROBLEM_CLASSES = (
    "contract-schema-gap",
    "doom-loop",
    "enrich-gate-reject",
    "other",
    "promotion-gate-unmet",
    "unknown-library",
    "unresolved-error",
)


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


def _rec(
    state: str,
    problem_class: str,
    *,
    enrichment: dict | None = None,
    resolved_at: str | None = None,
    fp_suffix: str = "0",
    **over: object,
) -> dict:
    """Return a minimal schema-valid escalation record dict."""
    fingerprint = _FP_BASE[: -len(fp_suffix)] + fp_suffix
    rec: dict = {
        "schema_version": 1,
        "fingerprint": fingerprint,
        "state": state,
        "problem_class": problem_class,
        "tried": [{"approach": "a"}],
        "evidence": [{"run_id": "r", "snippet": "s"}],
        "suggested_enrich_query": "q",
        "first_seen": "2026-06-15T00:00:00Z",
        "last_seen": "2026-06-15T00:00:00Z",
        "occurrences": 1,
        "distinct_runs": 1,
        "plugin_version": "0.9.0",
        "repo_fingerprint": "abc123",
    }
    if enrichment is not None:
        rec["enrichment"] = enrichment
    if resolved_at is not None:
        rec["resolved_at"] = resolved_at
    rec.update(over)
    return rec


def _enrich_block(written: int = 2) -> dict:
    return {
        "query": "q",
        "enriched_at": "2026-06-15T00:00:00Z",
        "retrieved_date": "2026-06-15",
        "counts": {
            "admitted": 1,
            "rejected": 0,
            "written": written,
            "unchanged": 0,
        },
    }


# ---------------------------------------------------------------------------
# 1. Fixture validity — prove fixtures pass schema validation
# ---------------------------------------------------------------------------


def test_fixtures_are_schema_valid() -> None:
    """Core record fixtures must pass validate_escalation (no mocking)."""
    for state in _ALL_STATES:
        if state == "resolved":
            r = _rec(state, "doom-loop", resolved_at="2026-06-15T00:00:00Z")
        elif state == "abandoned":
            r = _rec(state, "doom-loop", resolved_at="2026-06-15T00:00:00Z")
        elif state == "enriched":
            r = _rec(state, "doom-loop", enrichment=_enrich_block())
        else:
            r = _rec(state, "doom-loop")
        validate_escalation(r)  # must not raise


# ---------------------------------------------------------------------------
# 2. Empty list → all-zeros, no ZeroDivisionError
# ---------------------------------------------------------------------------


def test_empty_list_all_zeros() -> None:
    """measure([]) must return all-zero counts with no ZeroDivisionError."""
    result = me.measure([])

    assert result["total"] == 0
    assert result["resolved"] == 0
    assert result["abandoned"] == 0
    assert result["pending"] == 0
    assert result["resolution_rate_pct"] == 0.0
    assert result["recovery_rate_pct"] == 0.0
    assert result["enrich_attempted"] == 0
    assert result["enrichment_pages_written"] == 0

    # All 4 state keys always present and zero
    for key in _ALL_STATES:
        assert result["by_state"][key] == 0, f"by_state[{key!r}] should be 0"

    # All 7 problem_class keys always present and zero
    for key in _ALL_PROBLEM_CLASSES:
        assert result["by_problem_class"][key] == 0, (
            f"by_problem_class[{key!r}] should be 0"
        )


# ---------------------------------------------------------------------------
# 3. by_state counts across all 4 states
# ---------------------------------------------------------------------------


def test_by_state_counts() -> None:
    """by_state correctly counts across all 4 states; unseen states stay 0."""
    records = [
        _rec("open", "doom-loop", fp_suffix="1"),
        _rec("open", "doom-loop", fp_suffix="2"),
        _rec("enriched", "doom-loop", enrichment=_enrich_block(), fp_suffix="3"),
        _rec("resolved", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="4"),
        _rec("abandoned", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="5"),
    ]
    result = me.measure(records)

    assert result["total"] == 5
    assert result["by_state"]["open"] == 2
    assert result["by_state"]["enriched"] == 1
    assert result["by_state"]["resolved"] == 1
    assert result["by_state"]["abandoned"] == 1


# ---------------------------------------------------------------------------
# 4. by_problem_class counts; unseen keys stay 0
# ---------------------------------------------------------------------------


def test_by_problem_class_counts() -> None:
    """by_problem_class increments seen classes; unseen canonical keys stay 0."""
    records = [
        _rec("open", "doom-loop", fp_suffix="1"),
        _rec("open", "doom-loop", fp_suffix="2"),
        _rec("open", "contract-schema-gap", fp_suffix="3"),
        _rec("open", "unknown-library", fp_suffix="4"),
    ]
    result = me.measure(records)

    assert result["by_problem_class"]["doom-loop"] == 2
    assert result["by_problem_class"]["contract-schema-gap"] == 1
    assert result["by_problem_class"]["unknown-library"] == 1
    # Unseen canonical keys must be present and zero
    assert result["by_problem_class"]["enrich-gate-reject"] == 0
    assert result["by_problem_class"]["promotion-gate-unmet"] == 0
    assert result["by_problem_class"]["unresolved-error"] == 0
    assert result["by_problem_class"]["other"] == 0


def test_unknown_problem_class_ignored() -> None:
    """A record with a non-canonical problem_class is silently ignored; fixed keys intact."""
    r = _rec("open", "doom-loop", fp_suffix="1")
    r["problem_class"] = "totally-unknown-value"
    result = me.measure([r])

    # All 7 canonical keys present and zero (unknown value does not crash)
    for key in _ALL_PROBLEM_CLASSES:
        assert key in result["by_problem_class"]
        assert result["by_problem_class"][key] == 0


# ---------------------------------------------------------------------------
# 5. resolution_rate_pct: 2 resolved + 1 abandoned → 66.7
# ---------------------------------------------------------------------------


def test_resolution_rate_pct() -> None:
    """2 resolved + 1 abandoned → resolution_rate_pct == 66.7."""
    records = [
        _rec("resolved", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="1"),
        _rec("resolved", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="2"),
        _rec("abandoned", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="3"),
    ]
    result = me.measure(records)

    assert result["resolved"] == 2
    assert result["abandoned"] == 1
    assert result["resolution_rate_pct"] == 66.7


# ---------------------------------------------------------------------------
# 6. recovery_rate_pct: 2 resolved out of 5 total → 40.0
# ---------------------------------------------------------------------------


def test_recovery_rate_pct() -> None:
    """2 resolved out of 5 total → recovery_rate_pct == 40.0."""
    records = [
        _rec("resolved", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="1"),
        _rec("resolved", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="2"),
        _rec("open", "doom-loop", fp_suffix="3"),
        _rec("open", "doom-loop", fp_suffix="4"),
        _rec("abandoned", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="5"),
    ]
    result = me.measure(records)

    assert result["total"] == 5
    assert result["resolved"] == 2
    assert result["recovery_rate_pct"] == 40.0


# ---------------------------------------------------------------------------
# 7. pending == open + enriched
# ---------------------------------------------------------------------------


def test_pending_equals_open_plus_enriched() -> None:
    """pending must always equal by_state['open'] + by_state['enriched']."""
    records = [
        _rec("open", "doom-loop", fp_suffix="1"),
        _rec("enriched", "doom-loop", enrichment=_enrich_block(), fp_suffix="2"),
        _rec("enriched", "doom-loop", enrichment=_enrich_block(), fp_suffix="3"),
        _rec("resolved", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="4"),
    ]
    result = me.measure(records)

    assert result["pending"] == result["by_state"]["open"] + result["by_state"]["enriched"]
    assert result["pending"] == 3


# ---------------------------------------------------------------------------
# 8. enrich_attempted + enrichment_pages_written
# ---------------------------------------------------------------------------


def test_enrich_attempted_and_pages_written() -> None:
    """Records with enrichment dict increment enrich_attempted; pages sums written."""
    records = [
        _rec("enriched", "doom-loop", enrichment=_enrich_block(written=2), fp_suffix="1"),
        _rec("enriched", "doom-loop", enrichment=_enrich_block(written=3), fp_suffix="2"),
        _rec("open", "doom-loop", fp_suffix="3"),  # no enrichment block
    ]
    result = me.measure(records)

    assert result["enrich_attempted"] == 2
    assert result["enrichment_pages_written"] == 5  # 2 + 3


def test_no_enrichment_counts_zero() -> None:
    """Records without enrichment dict do not increment enrich_attempted or pages."""
    records = [_rec("open", "doom-loop", fp_suffix="1")]
    result = me.measure(records)

    assert result["enrich_attempted"] == 0
    assert result["enrichment_pages_written"] == 0


# ---------------------------------------------------------------------------
# 9. JSON serialisability
# ---------------------------------------------------------------------------


def test_result_is_json_serialisable() -> None:
    """measure() result must be json.dumps-able."""
    records = [
        _rec("open", "doom-loop", fp_suffix="1"),
        _rec("resolved", "doom-loop", resolved_at="2026-06-15T00:00:00Z", fp_suffix="2"),
    ]
    result = me.measure(records)
    dumped = json.dumps(result)  # must not raise
    loaded = json.loads(dumped)
    assert loaded["total"] == 2


# ---------------------------------------------------------------------------
# 10. Byte-stability: measure() source has no datetime.now / date.today / random
# ---------------------------------------------------------------------------


def test_measure_source_is_deterministic() -> None:
    """measure() must contain no datetime.now, date.today, or random calls."""
    src = inspect.getsource(me.measure)
    assert "datetime.now" not in src, "measure() must not call datetime.now()"
    assert "date.today" not in src, "measure() must not call date.today()"
    assert "random" not in src, "measure() must not call random"


# ---------------------------------------------------------------------------
# 11. Deterministic across shuffled input
# ---------------------------------------------------------------------------


def test_deterministic_across_shuffled_input() -> None:
    """measure(batch) == measure(shuffled_batch); json.dumps byte-identical."""
    batch = [
        _rec("open", "doom-loop", fp_suffix="1"),
        _rec("enriched", "contract-schema-gap", enrichment=_enrich_block(), fp_suffix="2"),
        _rec("resolved", "unknown-library", resolved_at="2026-06-15T00:00:00Z", fp_suffix="3"),
        _rec("abandoned", "other", resolved_at="2026-06-15T00:00:00Z", fp_suffix="4"),
        _rec("open", "promotion-gate-unmet", fp_suffix="5"),
    ]
    shuffled = copy.copy(batch)
    random.seed(99)
    random.shuffle(shuffled)

    r1 = me.measure(batch)
    r2 = me.measure(shuffled)

    assert r1 == r2, f"results differ: {r1} vs {r2}"
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True), (
        "json.dumps with sort_keys differ — sub-dicts not byte-stable"
    )


# ---------------------------------------------------------------------------
# 12. CLI smoke — real subprocess round-trip
# ---------------------------------------------------------------------------


def test_cli_smoke_real_records(tmp_path: Path) -> None:
    """CLI smoke: record + resolve via orchestrator, then measure-escalation → rc0 + JSON."""
    scripts_dir = ROOT / "scripts"

    # Create a record
    r = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "escalation-record",
            "--problem-class", "doom-loop",
            "--query", "q",
            "--approach", "a",
            "--run-id", "r",
            "--snippet", "s",
            "--repo-root", str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert r.returncode == 0, f"escalation-record failed:\nstdout={r.stdout}\nstderr={r.stderr}"

    # Get the fingerprint prefix
    created = json.loads(r.stdout.strip())
    prefix = str(created["fingerprint"])[:8]

    # Resolve it as abandoned
    r2 = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "escalation-resolve",
            prefix,
            "abandoned",
            "--repo-root", str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert r2.returncode == 0, (
        f"escalation-resolve failed:\nstdout={r2.stdout}\nstderr={r2.stderr}"
    )

    # Now measure
    r3 = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "measure-escalation",
            "--repo-root", str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert r3.returncode == 0, (
        f"measure-escalation failed:\nstdout={r3.stdout}\nstderr={r3.stderr}"
    )
    output = json.loads(r3.stdout.strip())
    assert output["total"] == 1
    assert output["by_state"]["abandoned"] == 1
    assert output["by_state"]["open"] == 0
    assert output["by_problem_class"]["doom-loop"] == 1


# ---------------------------------------------------------------------------
# 13. Missing ledger → rc0 + all-zeros
# ---------------------------------------------------------------------------


def test_missing_ledger_all_zeros(tmp_path: Path) -> None:
    """--repo-root pointing at an empty dir with no escalations → rc0 + all-zeros."""
    scripts_dir = ROOT / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "measure-escalation",
            "--repo-root", str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert result.returncode == 0, (
        f"expected rc0, got {result.returncode}\nstderr={result.stderr}"
    )
    output = json.loads(result.stdout.strip())
    assert output["total"] == 0
    assert output["resolution_rate_pct"] == 0.0
    assert output["recovery_rate_pct"] == 0.0
    for key in _ALL_STATES:
        assert output["by_state"][key] == 0
    for key in _ALL_PROBLEM_CLASSES:
        assert output["by_problem_class"][key] == 0
