"""Deterministic class+location oracle for the learning-loop A/B (Task 8).

No LLM, byte-stable. Scores a reviewer ``review.json`` against a single golden
``(class, file)`` defect, plus a noise count for clean-diff holdouts, plus a
SHA-256 evidence helper over the raw ``review.json`` bytes.

The catch criterion is a LOCATION match, not class-anywhere: a finding counts
only when its ``class`` equals the golden class AND its ``file`` equals the
golden file. This defends against the spoiler-leak confound (spec P0-1): a
reviewer that merely NAMES the class without locating it does not count.

``REVIEWER_FINDING_CLASSES`` is inline-frozen here (Archon host imports only the
vocab; the durable copy lives in ``scripts/learning_miner.py``). ``test_oracle.py``
imports the real one and asserts the two are identical (drift guard).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# Inline-frozen copy of scripts/learning_miner.py:58-66 REVIEWER_FINDING_CLASSES.
# Kept byte-identical by the drift test in test_oracle.py.
REVIEWER_FINDING_CLASSES: frozenset[str] = frozenset(
    {
        "index-out-of-bounds", "null-deref", "unguarded-empty-input",
        "off-by-one", "unchecked-return", "resource-leak", "race-condition",
        "injection", "missing-input-validation", "incorrect-error-handling",
        "type-confusion", "scope-violation", "missing-test",
        "spec-noncompliance", "doc-drift", "dead-code",
    }
)

# Severities the schema (schemas/review.schema.json) permits on a finding.
_NOISE_SEVERITIES: frozenset[str] = frozenset({"P2"})


def normalize_class(value: Any) -> str:
    """Normalize a finding ``class`` exactly as the miner does (learning_miner.py:148).

    Returns the lower-cased, stripped class when it is a string in the frozen
    vocab; otherwise the empty string (never a vocab member).
    """
    if not isinstance(value, str):
        return ""
    norm = value.strip().lower()
    return norm if norm in REVIEWER_FINDING_CLASSES else ""


def _iter_findings(review: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the review's findings list, tolerating a missing/malformed field."""
    findings = review.get("findings")
    if not isinstance(findings, list):
        return []
    return [f for f in findings if isinstance(f, dict)]


def caught(review: dict[str, Any], golden_class: str, golden_file: str) -> bool:
    """True iff some finding has class==golden_class AND file==golden_file.

    Location match, not class-anywhere. ``golden_class`` is normalized the same
    way as a finding's class so the comparison is canonical on both sides.
    """
    target_class = normalize_class(golden_class)
    if not target_class:
        return False
    for finding in _iter_findings(review):
        if normalize_class(finding.get("class")) != target_class:
            continue
        file_val = finding.get("file")
        if isinstance(file_val, str) and file_val == golden_file:
            return True
    return False


def noise_count(review: dict[str, Any]) -> int:
    """Count P2 / invalid findings — the noise signal on a clean holdout diff.

    A finding is noise when its ``severity`` is P2 (or any value outside the
    P0/P1 signal set, including a missing/malformed severity). On a clean diff
    every finding is by construction noise, so this is the per-arm noise number
    the driver compares ON vs OFF.
    """
    count = 0
    for finding in _iter_findings(review):
        severity = finding.get("severity")
        if not isinstance(severity, str) or severity in _NOISE_SEVERITIES or severity not in {"P0", "P1"}:
            count += 1
    return count


def load_review(path: str | Path) -> dict[str, Any]:
    """Load a review.json file into a dict (raises on malformed JSON / non-dict)."""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"review.json is not a JSON object: {path}")
    return data


def sha256_file(path: str | Path) -> str:
    """SHA-256 hex digest of a review.json file's raw bytes (evidence log).

    Reads bytes, never re-serializes, so the digest is reproducible by any
    `shasum -a 256 review.json` and survives whitespace/key-order.
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
