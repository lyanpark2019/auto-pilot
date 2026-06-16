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
