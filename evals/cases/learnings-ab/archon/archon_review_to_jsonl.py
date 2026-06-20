#!/usr/bin/env python3
"""archon_review_to_jsonl.py — Archon-side CAPTURE adapter.

Reads a reviewer ``review.json`` (shape
``{reviewer, verdict, findings:[{severity, title, detail, file, class}]}``) and
appends the qualifying findings to
``.planning/auto-pilot/critic-rejections-phase-0.jsonl`` in the
auto-pilot learning-miner input contract (see auto-pilot
``scripts/_capture_reviews.py`` and ``scripts/learning_miner.py``).

Mapping (verbatim from the spec + the miner's real input contract):
  - keep only ``verdict == "REJECT"`` findings with ``severity in {"P0","P1"}``
  - ``issue`` <- ``finding.title``
  - ``file`` made repo-relative (empty file dropped)
  - ``class`` carried ONLY when in ``REVIEWER_FINDING_CLASSES`` (the ``"none"``
    sentinel and any out-of-vocab tag are dropped — a class-less line keeps a
    byte-identical canonical dedupe key)
  - ``candidate_asset`` always ``null``
  - ``run_id`` from the ``RUN_ID`` env var
  - dedupe on ``canon_key = json.dumps(line, sort_keys=True)``

Emitted JSONL line fields: ``{file, issue, candidate_asset:null, run_id, class?}``.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# FROZEN copy of learning_miner.REVIEWER_FINDING_CLASSES (16 items). The Archon
# host does not import auto-pilot at runtime, so the vocab is inlined; a drift
# test (test_archon_review_to_jsonl.py) asserts this equals the live list.
REVIEWER_FINDING_CLASSES: frozenset[str] = frozenset(
    {
        "index-out-of-bounds", "null-deref", "unguarded-empty-input",
        "off-by-one", "unchecked-return", "resource-leak", "race-condition",
        "injection", "missing-input-validation", "incorrect-error-handling",
        "type-confusion", "scope-violation", "missing-test",
        "spec-noncompliance", "doc-drift", "dead-code",
    }
)

JSONL_REL = Path(".planning") / "auto-pilot" / "critic-rejections-phase-0.jsonl"


def _repo_relative(file_str: str, repo_root: Path) -> str:
    """Repo-relative form of ``file_str``; strips ``./``; passes through out-of-repo."""
    if not file_str:
        return file_str
    p = Path(file_str)
    if p.is_absolute():
        try:
            return str(p.relative_to(repo_root))
        except ValueError:
            return file_str
    raw = str(p)
    return raw[2:] if raw.startswith("./") else raw


def build_lines(review: dict[str, Any], repo_root: Path, run_id: str) -> list[dict[str, Any]]:
    """Map a review.json dict to qualifying critic-rejection JSONL line dicts."""
    if review.get("verdict") != "REJECT":
        return []
    raw_findings = review.get("findings", [])
    findings = raw_findings if isinstance(raw_findings, list) else []
    lines: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("severity") not in {"P0", "P1"}:
            continue
        title = finding.get("title", "")
        issue = title if isinstance(title, str) else str(title)
        file_raw = finding.get("file", "")
        file_str = _repo_relative(file_raw if isinstance(file_raw, str) else str(file_raw), repo_root)
        if not file_str:
            continue
        line: dict[str, Any] = {
            "file": file_str,
            "issue": issue,
            "candidate_asset": None,
            "run_id": run_id,
        }
        cls = finding.get("class")
        if isinstance(cls, str) and cls.strip().lower() in REVIEWER_FINDING_CLASSES:
            line["class"] = cls.strip().lower()
        lines.append(line)
    return lines


def append_jsonl(lines: list[dict[str, Any]], jsonl_path: Path) -> int:
    """Append non-duplicate lines (canon_key dedupe), return count of NEW lines."""
    existing: set[str] = set()
    if jsonl_path.exists():
        for raw in jsonl_path.read_text().splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                existing.add(json.dumps(json.loads(raw), sort_keys=True))
            except json.JSONDecodeError:
                continue
    new_text: list[str] = []
    seen = set(existing)
    for line in lines:
        canon = json.dumps(line, sort_keys=True)
        if canon in seen:
            continue
        seen.add(canon)
        new_text.append(json.dumps(line))
    if not new_text:
        return 0
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a") as fh:
        for text in new_text:
            fh.write(text + "\n")
    return len(new_text)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 1:
        sys.stderr.write("usage: archon_review_to_jsonl.py <review.json> [repo_root]\n")
        return 2
    review_path = Path(argv[0])
    repo_root = Path(argv[1]).resolve() if len(argv) > 1 else Path.cwd().resolve()
    run_id = os.environ.get("RUN_ID", "")
    review = json.loads(review_path.read_text())
    lines = build_lines(review, repo_root, run_id)
    appended = append_jsonl(lines, repo_root / JSONL_REL)
    sys.stdout.write(json.dumps({"appended": appended}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
