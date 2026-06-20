"""Tests for the deterministic class+location oracle (Task 8).

Golden fixtures cover: (a) finding at right class+file -> caught True;
(b) right class, WRONG file -> caught False; (c) P2 noise on a clean diff ->
noise==N; (d) SHA recompute matches. Plus the frozen-vocab drift guard.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
# evals/cases/learnings-ab -> repo root is three levels up.
_REPO_ROOT = _THIS_DIR.parents[2]
sys.path.insert(0, str(_THIS_DIR))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import oracle  # noqa: E402


def _finding(severity: str, file: str, cls: str | None) -> dict[str, object]:
    f: dict[str, object] = {
        "severity": severity,
        "file": file,
        "issue": f"a {cls or 'plain'} problem in {file}",
        "fix": "fix it",
        "finding_hash": "0" * 64,
    }
    if cls is not None:
        f["class"] = cls
    return f


def _review(findings: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "reviewer": "claude",
        "contract_id": "c1",
        "verdict": "REJECT",
        "scope_check": "PASS",
        "findings": findings,
        "verify_rerun": {"cmd": "pytest", "exit_code": 1},
        "reviewer_meta": {
            "model": "claude",
            "started_at": "2026-06-20T00:00:00Z",
            "ended_at": "2026-06-20T00:01:00Z",
        },
    }


# (a) finding at right class + right file -> caught True
def test_caught_right_class_right_file() -> None:
    review = _review([_finding("P1", "src/parser.py", "off-by-one")])
    assert oracle.caught(review, "off-by-one", "src/parser.py") is True


# (b) right class, WRONG file -> caught False (location match, not class-anywhere)
def test_not_caught_right_class_wrong_file() -> None:
    review = _review([_finding("P1", "src/other.py", "off-by-one")])
    assert oracle.caught(review, "off-by-one", "src/parser.py") is False


# right file, WRONG class -> caught False
def test_not_caught_wrong_class_right_file() -> None:
    review = _review([_finding("P1", "src/parser.py", "null-deref")])
    assert oracle.caught(review, "off-by-one", "src/parser.py") is False


# class normalization (case / trailing space) mirrors the miner
def test_caught_normalizes_class() -> None:
    review = _review([_finding("P0", "src/parser.py", "  Off-By-One  ")])
    assert oracle.caught(review, "OFF-BY-ONE", "src/parser.py") is True


# a class outside the frozen vocab never matches
def test_out_of_vocab_class_never_caught() -> None:
    review = _review([_finding("P1", "src/parser.py", "not-a-real-class")])
    assert oracle.caught(review, "not-a-real-class", "src/parser.py") is False


# empty / no findings -> not caught, zero noise
def test_empty_findings() -> None:
    review = _review([])
    assert oracle.caught(review, "off-by-one", "src/parser.py") is False
    assert oracle.noise_count(review) == 0


# (c) P2 noise on a clean diff -> noise == N (3 P2 findings)
def test_noise_count_p2_on_clean() -> None:
    findings = [
        _finding("P2", "a.py", "doc-drift"),
        _finding("P2", "b.py", "dead-code"),
        _finding("P2", "c.py", None),
    ]
    review = _review(findings)
    assert oracle.noise_count(review) == 3


# P0/P1 signal findings are NOT noise; only P2/invalid are counted
def test_noise_excludes_signal() -> None:
    findings: list[dict[str, object]] = [
        _finding("P0", "a.py", "injection"),
        _finding("P1", "b.py", "off-by-one"),
        _finding("P2", "c.py", "doc-drift"),
        _finding("bogus", "d.py", None),  # invalid severity -> noise
        {"file": "e.py"},                  # missing severity -> noise
    ]
    review = _review(findings)
    assert oracle.noise_count(review) == 3


# (d) SHA recompute matches a freshly-written review.json file
def test_sha256_file_recompute(tmp_path: Path) -> None:
    review = _review([_finding("P1", "src/parser.py", "off-by-one")])
    path = tmp_path / "review.json"
    raw = json.dumps(review, indent=2)
    path.write_text(raw)

    digest = oracle.sha256_file(path)
    # recompute over the same bytes
    assert digest == hashlib.sha256(raw.encode()).hexdigest()
    # second read is stable (byte-stable evidence log)
    assert oracle.sha256_file(path) == digest


# SHA matches the OS `shasum -a 256` (reproducible by the evidence log consumer)
def test_sha256_file_matches_shasum(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    path.write_bytes(b'{"findings": []}\n')
    out = subprocess.run(
        ["shasum", "-a", "256", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.split()[0]
    assert oracle.sha256_file(path) == out


# load_review round-trips a file then scores it
def test_load_review_then_caught(tmp_path: Path) -> None:
    review = _review([_finding("P1", "x.py", "race-condition")])
    path = tmp_path / "review.json"
    path.write_text(json.dumps(review))
    loaded = oracle.load_review(path)
    assert oracle.caught(loaded, "race-condition", "x.py") is True


def test_load_review_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "review.json"
    path.write_text("[1, 2, 3]")
    with pytest.raises(ValueError):
        oracle.load_review(path)


# drift guard: the inline-frozen vocab must equal the real miner's vocab
def test_vocab_frozen_against_miner() -> None:
    import learning_miner

    assert oracle.REVIEWER_FINDING_CLASSES == learning_miner.REVIEWER_FINDING_CLASSES
