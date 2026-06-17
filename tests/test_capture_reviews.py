"""Unit tests for scripts/_capture_reviews.py.

Covers: verdict filter, severity filter, key shape, path normalisation,
idempotency, cross-reviewer dedup, and malformed-input tolerance.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the scripts/ directory is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _capture_reviews


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FINDING_HASH = "a" * 64


def _make_review(
    verdict: str,
    findings: list[dict],
    *,
    reviewer: str = "auto-pilot-codex-reviewer",
    contract_id: str = "iter-1/phase-1/contract-1/round-1",
) -> dict:
    return {
        "schema_version": 1,
        "reviewer": reviewer,
        "contract_id": contract_id,
        "verdict": verdict,
        "scope_check": "PASS",
        "scope_drift_files": [],
        "scope_reduction_detected": False,
        "findings": findings,
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


def _round_dir(repo: Path, *, iter_n: int = 1, phase: int = 1,
               contract: int = 1, round_n: int = 1) -> Path:
    return (
        repo / ".planning" / "auto-pilot" / "contracts"
        / f"iter-{iter_n}" / f"phase-{phase}"
        / f"contract-{contract}" / f"round-{round_n}"
    )


def _write_signature(round_dir: Path, run_id: str) -> None:
    """Write a minimal PM-SIGNATURE (run_id is all _provenance_run_id reads)."""
    round_dir.mkdir(parents=True, exist_ok=True)
    (round_dir / "PM-SIGNATURE").write_text(json.dumps({"run_id": run_id}))


def _set_state(repo: Path, run_id: str) -> None:
    d = repo / ".planning" / "auto-pilot"
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({"run_id": run_id, "status": "running"}))


# ---------------------------------------------------------------------------
# (a) REJECT with P1 and P2 — only P1 written, keys exact
# ---------------------------------------------------------------------------

def test_reject_p1_kept_p2_dropped(tmp_path: Path) -> None:
    # Write state.json so run_id is stamped.
    (tmp_path / ".planning" / "auto-pilot").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".planning" / "auto-pilot" / "state.json").write_text(
        json.dumps({"run_id": "run-test-a", "status": "running"})
    )

    review = _make_review(
        "REJECT",
        [
            {"severity": "P1", "file": "scripts/foo.py", "line": 10,
             "issue": "unchecked None deref", "fix": "add guard",
             "finding_hash": _FINDING_HASH},
            {"severity": "P2", "file": "scripts/bar.py", "line": 20,
             "issue": "cosmetic nit", "fix": "rename", "finding_hash": "b" * 64},
        ],
    )
    review_path = _round_dir(tmp_path) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path, review)

    count = _capture_reviews.capture_phase(tmp_path, 1)
    assert count == 1

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    assert jsonl.exists()
    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1

    line = lines[0]
    # Exact key set: {file, issue, candidate_asset, run_id}.
    assert set(line.keys()) == {"file", "issue", "candidate_asset", "run_id"}
    assert line["file"] == "scripts/foo.py"
    assert line["issue"] == "unchecked None deref"
    assert line["candidate_asset"] is None
    assert line["run_id"] == "run-test-a"
    # Explicitly confirm dropped keys.
    assert "line" not in line
    assert "fix" not in line


# ---------------------------------------------------------------------------
# (b) APPROVE review → nothing written
# ---------------------------------------------------------------------------

def test_approve_review_nothing_written(tmp_path: Path) -> None:
    review = _make_review(
        "APPROVE",
        [{"severity": "P1", "file": "scripts/foo.py", "line": 1,
          "issue": "should not appear", "fix": "n/a",
          "finding_hash": _FINDING_HASH}],
    )
    review_path = _round_dir(tmp_path) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path, review)

    count = _capture_reviews.capture_phase(tmp_path, 1)
    assert count == 0

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    assert not jsonl.exists()


# ---------------------------------------------------------------------------
# (c) Absolute-path file → normalised to repo-relative
# ---------------------------------------------------------------------------

def test_absolute_path_normalised(tmp_path: Path) -> None:
    abs_file = str(tmp_path / "scripts" / "foo.py")
    review = _make_review(
        "REJECT",
        [{"severity": "P1", "file": abs_file, "line": 5,
          "issue": "some issue", "fix": "fix it",
          "finding_hash": _FINDING_HASH}],
    )
    review_path = _round_dir(tmp_path) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path, review)

    _capture_reviews.capture_phase(tmp_path, 1)

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert lines[0]["file"] == "scripts/foo.py"


# ---------------------------------------------------------------------------
# (d) Dedupe-on-append: second call appends 0 lines
# ---------------------------------------------------------------------------

def test_dedupe_on_append_idempotent(tmp_path: Path) -> None:
    review = _make_review(
        "REJECT",
        [{"severity": "P1", "file": "scripts/foo.py", "line": 10,
          "issue": "unchecked None deref", "fix": "add guard",
          "finding_hash": _FINDING_HASH}],
    )
    review_path = _round_dir(tmp_path) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path, review)

    count1 = _capture_reviews.capture_phase(tmp_path, 1)
    assert count1 == 1

    count2 = _capture_reviews.capture_phase(tmp_path, 1)
    assert count2 == 0

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    lines = [ln for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# (e) Cross-reviewer dup: codex + claude both REJECT same {file,issue} → 1 line
# ---------------------------------------------------------------------------

def test_cross_reviewer_dedup(tmp_path: Path) -> None:
    finding = {"severity": "P1", "file": "scripts/foo.py", "line": 10,
               "issue": "shared issue", "fix": "guard it",
               "finding_hash": _FINDING_HASH}
    rd = _round_dir(tmp_path)
    _write_review(rd / "outputs" / "codex-reviewer" / "review.json",
                  _make_review("REJECT", [finding]))
    _write_review(rd / "outputs" / "claude-reviewer" / "review.json",
                  _make_review("REJECT", [finding], reviewer="auto-pilot-claude-reviewer"))

    count = _capture_reviews.capture_phase(tmp_path, 1)
    assert count == 1

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    lines = [ln for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# (f) Malformed review.json → skipped, no crash, valid reviews still counted
# ---------------------------------------------------------------------------

def test_malformed_review_skipped(tmp_path: Path) -> None:
    # Write one valid REJECT review.
    rd = _round_dir(tmp_path)
    valid_review = _make_review(
        "REJECT",
        [{"severity": "P1", "file": "scripts/ok.py", "line": 1,
          "issue": "real issue", "fix": "real fix",
          "finding_hash": _FINDING_HASH}],
    )
    _write_review(rd / "outputs" / "codex-reviewer" / "review.json", valid_review)

    # Write a malformed file in a second contract.
    bad_path = _round_dir(tmp_path, contract=2) / "outputs" / "codex-reviewer" / "review.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{not valid json at all!!!")

    # Write a schema-invalid review (missing required fields) in a third contract.
    schema_invalid_path = (
        _round_dir(tmp_path, contract=3) / "outputs" / "codex-reviewer" / "review.json"
    )
    schema_invalid_path.parent.mkdir(parents=True, exist_ok=True)
    schema_invalid_path.write_text(json.dumps({"verdict": "REJECT"}))

    count = _capture_reviews.capture_phase(tmp_path, 1)
    # Only the one valid REJECT finding makes it through.
    assert count == 1

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0]["file"] == "scripts/ok.py"


# ---------------------------------------------------------------------------
# (g) state.json present → captured line carries that run_id
# ---------------------------------------------------------------------------

def test_run_id_stamped_from_state_json(tmp_path: Path) -> None:
    (tmp_path / ".planning" / "auto-pilot").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".planning" / "auto-pilot" / "state.json").write_text(
        json.dumps({"run_id": "run-xyz", "status": "running"})
    )
    review = _make_review(
        "REJECT",
        [{"severity": "P1", "file": "scripts/foo.py", "line": 1,
          "issue": "some issue", "fix": "fix it",
          "finding_hash": _FINDING_HASH}],
    )
    review_path = _round_dir(tmp_path) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path, review)

    _capture_reviews.capture_phase(tmp_path, 1)

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0]["run_id"] == "run-xyz"


# ---------------------------------------------------------------------------
# (h) No state.json → captured line run_id is "" (acceptable; miner treats
#     empty run_id as non-persisting — falls back to state run_id which is also
#     "" → dry-run mode)
# ---------------------------------------------------------------------------

def test_run_id_empty_when_no_state_json(tmp_path: Path) -> None:
    # Do NOT create state.json — current_run_id returns "".
    review = _make_review(
        "REJECT",
        [{"severity": "P1", "file": "scripts/baz.py", "line": 5,
          "issue": "missing check", "fix": "add check",
          "finding_hash": _FINDING_HASH}],
    )
    review_path = _round_dir(tmp_path) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path, review)

    _capture_reviews.capture_phase(tmp_path, 1)

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0]["run_id"] == "", (
        "absent state.json → current_run_id returns '' → line run_id must be ''"
    )


# ---------------------------------------------------------------------------
# (i) PM-SIGNATURE present → captured line carries the PROVENANCE run_id,
#     not the scan-time state run_id
# ---------------------------------------------------------------------------

def test_provenance_run_id_overrides_state(tmp_path: Path) -> None:
    _set_state(tmp_path, "state-run")          # scan-time run_id
    rd = _round_dir(tmp_path)
    _write_signature(rd, "sig-run")            # run that PRODUCED the review
    review = _make_review(
        "REJECT",
        [{"severity": "P1", "file": "scripts/foo.py", "line": 1,
          "issue": "some issue", "fix": "fix it", "finding_hash": _FINDING_HASH}],
    )
    _write_review(rd / "outputs" / "codex-reviewer" / "review.json", review)

    _capture_reviews.capture_phase(tmp_path, 1)

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0]["run_id"] == "sig-run", "provenance (PM-SIGNATURE) must win over state run_id"


def test_provenance_missing_signature_falls_back_to_state(tmp_path: Path) -> None:
    _set_state(tmp_path, "state-run")
    rd = _round_dir(tmp_path)                   # no PM-SIGNATURE written
    review_path = rd / "outputs" / "codex-reviewer" / "review.json"
    assert _capture_reviews._provenance_run_id(review_path, "state-run") == "state-run"


# ---------------------------------------------------------------------------
# (j) Cross-session re-scan must NOT inflate — the inflation regression lock.
#     A persisted review.json re-swept in a LATER session (different state
#     run_id) reads the SAME provenance run_id from PM-SIGNATURE → identical
#     canonical key → deduped → no 2nd line.
# ---------------------------------------------------------------------------

def test_cross_session_rescan_no_inflation(tmp_path: Path) -> None:
    rd = _round_dir(tmp_path)
    _write_signature(rd, "run-A")              # the review was produced by run-A
    review = _make_review(
        "REJECT",
        [{"severity": "P1", "file": "scripts/foo.py", "line": 10,
          "issue": "unchecked None deref", "fix": "add guard", "finding_hash": _FINDING_HASH}],
    )
    _write_review(rd / "outputs" / "codex-reviewer" / "review.json", review)

    # Session A captures.
    _set_state(tmp_path, "run-A")
    assert _capture_reviews.capture_phase(tmp_path, 1) == 1

    # Session B (later) re-sweeps the SAME persisted review under a new state run_id.
    _set_state(tmp_path, "run-B")
    assert _capture_reviews.capture_phase(tmp_path, 1) == 0, (
        "re-scan of a persisted review must add 0 lines (provenance run_id is stable)"
    )

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0]["run_id"] == "run-A"


# ---------------------------------------------------------------------------
# (k) capture_all_phases sweeps every phase under the contracts tree
# ---------------------------------------------------------------------------

def test_capture_all_phases_sweeps_multiple(tmp_path: Path) -> None:
    _set_state(tmp_path, "run-1")
    for phase in (1, 2):
        rd = _round_dir(tmp_path, phase=phase)
        _write_review(
            rd / "outputs" / "codex-reviewer" / "review.json",
            _make_review(
                "REJECT",
                [{"severity": "P1", "file": f"scripts/p{phase}.py", "line": 1,
                  "issue": f"issue in phase {phase}", "fix": "x",
                  "finding_hash": _FINDING_HASH}],
                contract_id=f"iter-1/phase-{phase}/contract-1/round-1",
            ),
        )

    total = _capture_reviews.capture_all_phases(tmp_path)
    assert total == 2
    planning = tmp_path / ".planning" / "auto-pilot"
    assert (planning / "critic-rejections-phase-1.jsonl").exists()
    assert (planning / "critic-rejections-phase-2.jsonl").exists()


# ---------------------------------------------------------------------------
# R1: a reviewer-emitted controlled-vocab `class` survives capture into JSONL
# ---------------------------------------------------------------------------

def test_class_carried_to_jsonl_when_present(tmp_path: Path) -> None:
    """A finding's `class` is carried into the JSONL line; a finding without it
    keeps the exact 4-key shape (class-less canonical dedup key unchanged)."""
    _set_state(tmp_path, "run-class")
    review = _make_review(
        "REJECT",
        [
            {"severity": "P1", "file": "metrics.py", "line": 5,
             "issue": "p=1.0 IndexError", "class": "index-out-of-bounds",
             "fix": "use len-1", "finding_hash": _FINDING_HASH},
            {"severity": "P1", "file": "other.py", "line": 9,
             "issue": "no class here", "fix": "x", "finding_hash": "c" * 64},
        ],
    )
    review_path = _round_dir(tmp_path) / "outputs" / "codex-reviewer" / "review.json"
    _write_review(review_path, review)

    count = _capture_reviews.capture_phase(tmp_path, 1)
    assert count == 2

    jsonl = tmp_path / ".planning" / "auto-pilot" / "critic-rejections-phase-1.jsonl"
    lines = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    by_file = {ln["file"]: ln for ln in lines}
    assert by_file["metrics.py"]["class"] == "index-out-of-bounds"
    assert "class" not in by_file["other.py"]
    assert set(by_file["other.py"].keys()) == {"file", "issue", "candidate_asset", "run_id"}
