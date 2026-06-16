"""Organic 2-run proof for the capture → mine → resolve pipeline.

Only the review.json inputs are fixtures; producer, miner, resolver, and
measure are all production code.  NO synthetic _improvement.bump_or_create
seeding.

Pipeline exercised end-to-end:
  capture_phase (write JSONL from review.json, each line stamped with run_id)
  → run_miner   (scan JSONL, credit each line to ITS OWN run_id)
  → resolve_learnings (inject gate-passed learnings)
  → measure      (scope_addressable_pct == 100.0)
  + provenance verification

The proof is GENUINE per-run recurrence: run-B writes its OWN new review.json
(contract-2) and calls capture_phase again, appending a second JSONL line
stamped run-B.  This contrasts with the false-promotion path where only the
state run_id is flipped and the miner re-reads the SAME line under the new id.

test_stale_finding_not_recredited_to_new_run is the anti-inflation guard: it
proves that flipping state run_id WITHOUT a new capture does NOT increment
distinct_runs, because the existing JSONL line carries run_id=run-A and the
miner credits run-A regardless of what state.json says.
"""
from __future__ import annotations

import json
import sys
import unittest.mock as mock
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Make scripts/ importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _capture_reviews
import _improvement
import _learnings
import learning_miner
import measure_learnings_injection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINDING_HASH_1 = "a" * 64
_FINDING_HASH_2 = "b" * 64


def _make_reject_review(
    finding_hash: str = _FINDING_HASH_1,
    *,
    file: str = "scripts/foo.py",
    issue: str = "unchecked None deref",
    reviewer: str = "auto-pilot-codex-reviewer",
) -> dict:
    return {
        "schema_version": 1,
        "reviewer": reviewer,
        "contract_id": "iter-1/phase-1/contract-1/round-1",
        "verdict": "REJECT",
        "scope_check": "PASS",
        "scope_drift_files": [],
        "scope_reduction_detected": False,
        "findings": [
            {
                "severity": "P1",
                "file": file,
                "line": 10,
                "issue": issue,
                "fix": "add guard",
                "finding_hash": finding_hash,
            }
        ],
        "verify_rerun": {"cmd": "pytest -q", "exit_code": 1},
        "reviewer_meta": {
            "model": "test",
            "started_at": "2026-06-16T00:00:00+00:00",
            "ended_at": "2026-06-16T00:00:01+00:00",
        },
    }


def _write_review(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _write_signature(round_dir: Path, run_id: str) -> None:
    """Write a minimal PM-SIGNATURE so capture stamps the PROVENANCE run_id."""
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "PM-SIGNATURE").write_text(json.dumps({"run_id": run_id}))


def _round_dir(repo: Path, *, iter_n: int = 1, phase: int = 1,
               contract: int = 1, round_n: int = 1) -> Path:
    return (
        repo / ".planning" / "auto-pilot" / "contracts"
        / f"iter-{iter_n}" / f"phase-{phase}"
        / f"contract-{contract}" / f"round-{round_n}"
    )


_T0 = datetime(2026, 6, 16, 0, 0, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 6, 16, 1, 0, 0, tzinfo=timezone.utc)


def _find_ticket_for_path(ledger: Path, source_path: str) -> "dict | None":
    """Locate the ledger ticket whose evidence references source_path."""
    for tp in sorted(ledger.glob("*.json")):
        try:
            t = json.loads(tp.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for ev in t.get("evidence", []):
            if isinstance(ev, dict) and ev.get("source_path") == source_path:
                return t
    return None


# ---------------------------------------------------------------------------
# Full 2-run GENUINE organic proof
# ---------------------------------------------------------------------------

def test_capture_mine_resolve_measure_two_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full pipeline: capture review.json → mine → resolve → measure (2 run_ids).

    run-B genuinely re-captures its own review.json (contract-2), producing a
    new JSONL line stamped run-B.  distinct_runs reaches 2 via actual recurrence.
    """
    # Redirect HOME so local_key() writes its attest.key under tmp_path, not ~/.claude.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    repo = tmp_path / "repo"
    repo.mkdir()
    planning = repo / ".planning" / "auto-pilot"
    planning.mkdir(parents=True)
    tmp_ledger = tmp_path / "ledger"

    # -----------------------------------------------------------------------
    # run-A: state.json run_id="run-A" + one REJECT review under contract-1
    # -----------------------------------------------------------------------
    (planning / "state.json").write_text(
        json.dumps({"run_id": "run-A", "status": "running"})
    )
    review_path_a = _round_dir(repo, contract=1) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path_a, _make_reject_review(finding_hash=_FINDING_HASH_1))

    count_a = _capture_reviews.capture_phase(repo, 1)
    assert count_a == 1, f"expected 1 new JSONL line for run-A, got {count_a}"

    jsonl = planning / "critic-rejections-phase-1.jsonl"
    assert jsonl.exists(), "JSONL file must be created"
    lines_a = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines_a) == 1

    # Verify line shape: 4 keys including run_id.
    line_a = lines_a[0]
    assert set(line_a.keys()) == {"file", "issue", "candidate_asset", "run_id"}
    assert line_a["file"] == "scripts/foo.py"
    assert line_a["issue"] == "unchecked None deref"
    assert line_a["candidate_asset"] is None
    assert line_a["run_id"] == "run-A"
    assert "line" not in line_a, "'line' key must be dropped"

    # run_miner under run-A → distinct_runs==1, NOT yet promotable.
    result_a = learning_miner.run_miner(
        repo, commit_to=tmp_ledger, now=_T0, dry_run=False
    )
    assert result_a["candidates"] >= 1

    all_tickets = list(tmp_ledger.glob("*.json"))
    assert all_tickets, "ledger must contain at least one ticket file"

    target_ticket = _find_ticket_for_path(tmp_ledger, "scripts/foo.py")
    assert target_ticket is not None, (
        "miner must create a ticket for the captured finding; "
        f"ledger files: {[tp.name for tp in all_tickets]}"
    )
    assert target_ticket.get("distinct_runs") == 1
    assert not learning_miner.is_promotable(target_ticket), (
        "ticket should NOT be promotable after only 1 distinct run "
        f"(got distinct_runs={target_ticket.get('distinct_runs')})"
    )

    # -----------------------------------------------------------------------
    # Idempotency: re-capture under run-A → 0 new lines (identical run_id in key)
    # -----------------------------------------------------------------------
    count_a2 = _capture_reviews.capture_phase(repo, 1)
    assert count_a2 == 0, f"second capture must append 0 (idempotent); got {count_a2}"
    lines_check = [ln for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines_check) == 1, "JSONL must still have exactly 1 line after idempotent capture"

    # Re-mine under run-A → distinct_runs still 1 (same run_id → evidence (run_id, snippet) already counted).
    learning_miner.run_miner(repo, commit_to=tmp_ledger, now=_T0, dry_run=False)
    target_ticket_check = _find_ticket_for_path(tmp_ledger, "scripts/foo.py")
    assert target_ticket_check is not None
    assert target_ticket_check.get("distinct_runs") == 1, (
        "re-mining under the same run_id must not inflate distinct_runs"
    )

    # -----------------------------------------------------------------------
    # run-B GENUINE recurrence: flip state to run-B; write a NEW review.json
    # under contract-2 (same defect, new finding_hash = represents recurrence)
    # and call capture_phase again to stamp it with run-B.
    # -----------------------------------------------------------------------
    (planning / "state.json").write_text(
        json.dumps({"run_id": "run-B", "status": "running"})
    )
    # NEW review under contract-2 — the same file+issue, different finding_hash.
    review_path_b = _round_dir(repo, contract=2) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path_b, _make_reject_review(finding_hash=_FINDING_HASH_2))

    count_b = _capture_reviews.capture_phase(repo, 1)
    # The run-B line (same file+issue but run_id=run-B) differs from run-A line.
    assert count_b == 1, (
        f"run-B capture must append 1 new line (different run_id in canon key); got {count_b}"
    )

    lines_b = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines_b) == 2, f"JSONL must now have 2 lines (run-A + run-B); got {len(lines_b)}"
    run_ids_in_jsonl = {ln["run_id"] for ln in lines_b}
    assert run_ids_in_jsonl == {"run-A", "run-B"}, (
        f"JSONL must contain exactly run-A and run-B stamped lines; got {run_ids_in_jsonl}"
    )

    # run_miner under run-B: the run-B line carries run_id=run-B → new evidence entry.
    learning_miner.run_miner(repo, commit_to=tmp_ledger, now=_T1, dry_run=False)

    target_ticket_b = _find_ticket_for_path(tmp_ledger, "scripts/foo.py")
    assert target_ticket_b is not None
    assert target_ticket_b.get("distinct_runs") == 2, (
        f"after run-B genuine recurrence, distinct_runs must be 2; "
        f"got {target_ticket_b.get('distinct_runs')}"
    )
    assert learning_miner.is_promotable(target_ticket_b), (
        "ticket must be promotable after 2 distinct runs (threshold=2)"
    )
    assert _learnings.is_gate_passed(target_ticket_b), (
        "is_gate_passed must agree with is_promotable for a 2-distinct-run ticket"
    )

    # -----------------------------------------------------------------------
    # resolve_learnings (via monkeypatched ledger_dir)
    # -----------------------------------------------------------------------
    dest_dir = tmp_path / "bundle-dest"
    with mock.patch("_learnings.ledger_dir", return_value=tmp_ledger):
        result_path = _learnings.resolve_learnings(repo, ["scripts/"], dest_dir)

    assert result_path is not None, "resolve_learnings must return a path when a matching ticket exists"
    assert result_path.exists()
    assert result_path.name == "learnings.md"
    content = result_path.read_text()
    assert "unchecked None deref" in content, (
        "learnings.md must contain the ticket's issue text"
    )

    # -----------------------------------------------------------------------
    # measure: scope_addressable_pct == 100.0
    # -----------------------------------------------------------------------
    measure_result = measure_learnings_injection.measure(tmp_ledger, ["scripts/"])
    assert measure_result["scope_addressable_pct"] == 100.0, (
        f"scope_addressable_pct must be 100.0; got {measure_result['scope_addressable_pct']}"
    )

    # Flip check: empty ledger → 0.0
    empty_ledger = tmp_path / "empty-ledger"
    empty_result = measure_learnings_injection.measure(empty_ledger, ["scripts/"])
    assert empty_result["scope_addressable_pct"] == 0.0

    # -----------------------------------------------------------------------
    # provenance: verify_ticket_provenance returns ok=True
    # -----------------------------------------------------------------------
    key = _improvement.local_key()
    ok, reason = _improvement.verify_ticket_provenance(target_ticket_b, key=key)
    assert ok, (
        f"provenance check must return ok=True; got ok={ok}, reason={reason!r}"
    )


# ---------------------------------------------------------------------------
# Sweep-path + provenance proof: capture_all_phases (the Stop-hook code path),
# genuine 2-run recurrence stamped via PM-SIGNATURE, inflation-safe across
# re-sweeps, 0 -> 100 scope_addressable_pct.
# ---------------------------------------------------------------------------

def test_capture_all_phases_organic_two_runs_with_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive capture via capture_all_phases (what the Stop hook calls), with each
    run's review signed by its OWN PM-SIGNATURE run_id.  Proves: (1) genuine 2-run
    recurrence promotes, (2) re-sweeping persisted reviews adds 0 lines (provenance
    is stable, no inflation), (3) scope_addressable_pct flips 0 -> 100.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    repo = tmp_path / "repo"
    repo.mkdir()
    planning = repo / ".planning" / "auto-pilot"
    planning.mkdir(parents=True)
    tmp_ledger = tmp_path / "ledger"
    jsonl = planning / "critic-rejections-phase-1.jsonl"

    # run-A: review under contract-1, signed run-A.
    (planning / "state.json").write_text(json.dumps({"run_id": "run-A", "status": "running"}))
    rd_a = _round_dir(repo, contract=1)
    _write_review(rd_a / "outputs" / "codex-reviewer" / "review.json",
                  _make_reject_review(finding_hash=_FINDING_HASH_1))
    _write_signature(rd_a, "run-A")

    assert _capture_reviews.capture_all_phases(repo) == 1
    # Re-sweep within run-A → 0 (provenance run-A is stable).
    assert _capture_reviews.capture_all_phases(repo) == 0

    learning_miner.run_miner(repo, commit_to=tmp_ledger, now=_T0, dry_run=False)
    t_a = _find_ticket_for_path(tmp_ledger, "scripts/foo.py")
    assert t_a is not None and t_a.get("distinct_runs") == 1
    assert not learning_miner.is_promotable(t_a)

    # run-B genuine recurrence: NEW review under contract-2, signed run-B.
    (planning / "state.json").write_text(json.dumps({"run_id": "run-B", "status": "running"}))
    rd_b = _round_dir(repo, contract=2)
    _write_review(rd_b / "outputs" / "codex-reviewer" / "review.json",
                  _make_reject_review(finding_hash=_FINDING_HASH_2))
    _write_signature(rd_b, "run-B")

    # Sweep re-scans contract-1 (sig run-A → already present, deduped) AND
    # contract-2 (sig run-B → new) → exactly 1 new line.
    assert _capture_reviews.capture_all_phases(repo) == 1
    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert {ln["run_id"] for ln in lines} == {"run-A", "run-B"}

    # Re-sweep again (later "session", state still run-B) → 0 new: BOTH reviews
    # carry stable provenance run_ids, so neither is re-stamped. Inflation closed.
    assert _capture_reviews.capture_all_phases(repo) == 0

    learning_miner.run_miner(repo, commit_to=tmp_ledger, now=_T1, dry_run=False)
    t_b = _find_ticket_for_path(tmp_ledger, "scripts/foo.py")
    assert t_b is not None and t_b.get("distinct_runs") == 2
    assert learning_miner.is_promotable(t_b)
    assert _learnings.is_gate_passed(t_b)

    # resolve + measure: 0 -> 100.
    dest_dir = tmp_path / "bundle-dest"
    with mock.patch("_learnings.ledger_dir", return_value=tmp_ledger):
        result_path = _learnings.resolve_learnings(repo, ["scripts/"], dest_dir)
    assert result_path is not None and "unchecked None deref" in result_path.read_text()

    assert measure_learnings_injection.measure(tmp_ledger, ["scripts/"])["scope_addressable_pct"] == 100.0
    assert measure_learnings_injection.measure(tmp_path / "empty", ["scripts/"])["scope_addressable_pct"] == 0.0


# ---------------------------------------------------------------------------
# Anti-inflation guard: stale finding must NOT be recredited to a new run
# ---------------------------------------------------------------------------

def test_stale_finding_not_recredited_to_new_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flipping state run_id WITHOUT a new capture must NOT inflate distinct_runs.

    This is the core fix: the JSONL line carries run_id=run-A (stamped at
    capture time).  When the miner re-scans the file under state run_id=run-B,
    it reads the line's own run_id (run-A) and credits run-A — not run-B.
    So distinct_runs stays 1 and the ticket remains non-promotable.
    """
    # Redirect HOME so local_key() writes its attest.key under tmp_path, not ~/.claude.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    repo = tmp_path / "repo"
    repo.mkdir()
    planning = repo / ".planning" / "auto-pilot"
    planning.mkdir(parents=True)
    tmp_ledger = tmp_path / "ledger"

    # run-A: capture one finding.
    (planning / "state.json").write_text(
        json.dumps({"run_id": "run-A", "status": "running"})
    )
    review_path = _round_dir(repo) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path, _make_reject_review())

    count = _capture_reviews.capture_phase(repo, 1)
    assert count == 1

    learning_miner.run_miner(repo, commit_to=tmp_ledger, now=_T0, dry_run=False)
    ticket_a = _find_ticket_for_path(tmp_ledger, "scripts/foo.py")
    assert ticket_a is not None
    assert ticket_a.get("distinct_runs") == 1

    # Flip state to run-B but DO NOT capture anything new.
    # The JSONL still has only the run-A-stamped line.
    (planning / "state.json").write_text(
        json.dumps({"run_id": "run-B", "status": "running"})
    )

    # The JSONL line carries run_id="run-A" (stamped at capture time). The miner
    # reads that per-line run_id, so the (run_id, snippet) evidence pair is
    # identical to the first mine → already counted → distinct_runs stays 1.
    # Flipping state.json to run-B does NOT re-credit the stale line to run-B.
    learning_miner.run_miner(repo, commit_to=tmp_ledger, now=_T1, dry_run=False)

    ticket_b = _find_ticket_for_path(tmp_ledger, "scripts/foo.py")
    assert ticket_b is not None
    assert ticket_b.get("distinct_runs") == 1, (
        "distinct_runs must stay 1 when state run_id flips but no new capture occurred "
        f"(the line carries run_id=run-A; miner credits run-A, not run-B); "
        f"got distinct_runs={ticket_b.get('distinct_runs')}"
    )
    assert not learning_miner.is_promotable(ticket_b), (
        "ticket must NOT be promotable with only 1 distinct run (the inflation path is closed)"
    )
