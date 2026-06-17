"""tests/test_learning_miner_r1.py — R1 controlled-vocab `class` keying + edge fixes.

Split out of test_learning_miner.py (module-size budget). Covers: class-keyed
recurrence collapse, the causality control, out-of-vocab/variant normalization,
the doc↔code vocab drift lock, the any-value schema lock, the multi-file glob
OSError skip, and the empty-identity / whitespace-class edge fixes.
"""
from __future__ import annotations

import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import learning_miner as lm

NOW = datetime(2026, 6, 9, tzinfo=timezone.utc)


def _ledger_tickets(home_root: Path, repo_root: Path) -> list[dict]:
    slug = str(repo_root.resolve()).replace("/", "-")
    d = home_root / ".claude" / "projects" / slug / "improvements"
    return [json.loads(Path(f).read_text()) for f in glob.glob(str(d / "*.json"))]


def test_reviewer_class_collapses_phrasing_two_runs_promotable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1 regression-lock: ONE defect class, DIFFERENT issue wording across two
    runs, collapses to ONE fingerprint and reaches distinct_runs==2 (promotable).
    Pre-fix, free phrasing fragmented the key 1:1 → 0 promotable (R1 measure)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    (root / ".planning" / "auto-pilot").mkdir(parents=True)
    state = root / ".planning/auto-pilot/state.json"
    jsonl = root / ".planning/auto-pilot/critic-rejections-phase-1.jsonl"
    state.write_text(json.dumps({"run_id": "r1"}))
    jsonl.write_text(json.dumps(
        {"file": "metrics.py", "issue": "percentile() crashes at p=1.0 (IndexError)",
         "class": "index-out-of-bounds", "run_id": "r1"}) + "\n")
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"
    state.write_text(json.dumps({"run_id": "r2"}))
    with jsonl.open("a") as fh:
        fh.write(json.dumps(
            {"file": "metrics.py", "issue": "index out of range when p==1 in percentile()",
             "class": "index-out-of-bounds", "run_id": "r2"}) + "\n")
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "promotable"
    tickets = [t for t in _ledger_tickets(tmp_path / "home", root)
               if t.get("source") == "reviewer-finding"]
    assert len(tickets) == 1
    assert tickets[0]["distinct_runs"] == 2


def test_reviewer_no_class_phrasing_stays_fragmented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Causality control: WITHOUT a class, the same two phrasings fingerprint
    separately → two distinct_runs==1 tickets → never promotable. Proves the
    class tag (not something else) is what collapses recurrence."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    (root / ".planning" / "auto-pilot").mkdir(parents=True)
    state = root / ".planning/auto-pilot/state.json"
    jsonl = root / ".planning/auto-pilot/critic-rejections-phase-1.jsonl"
    state.write_text(json.dumps({"run_id": "r1"}))
    jsonl.write_text(json.dumps(
        {"file": "metrics.py", "issue": "percentile() crashes at p=1.0 (IndexError)",
         "run_id": "r1"}) + "\n")
    state.write_text(json.dumps({"run_id": "r2"}))
    with jsonl.open("a") as fh:
        fh.write(json.dumps(
            {"file": "metrics.py", "issue": "index out of range when p==1 in percentile()",
             "run_id": "r2"}) + "\n")
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"
    tickets = [t for t in _ledger_tickets(tmp_path / "home", root)
               if t.get("source") == "reviewer-finding"]
    assert len(tickets) == 2
    assert all(t["distinct_runs"] == 1 for t in tickets)


def test_reviewer_out_of_vocab_class_falls_back_to_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `class` outside REVIEWER_FINDING_CLASSES is ignored; keying falls back to
    the issue text. Same bogus class + different issue across runs → two tickets
    (proves it did NOT key on the unrecognised class)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    (root / ".planning" / "auto-pilot").mkdir(parents=True)
    state = root / ".planning/auto-pilot/state.json"
    jsonl = root / ".planning/auto-pilot/critic-rejections-phase-1.jsonl"
    state.write_text(json.dumps({"run_id": "r1"}))
    jsonl.write_text(json.dumps(
        {"file": "m.py", "issue": "bug A", "class": "totally-made-up", "run_id": "r1"}) + "\n")
    state.write_text(json.dumps({"run_id": "r2"}))
    with jsonl.open("a") as fh:
        fh.write(json.dumps(
            {"file": "m.py", "issue": "bug B", "class": "totally-made-up", "run_id": "r2"}) + "\n")
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"
    tickets = [t for t in _ledger_tickets(tmp_path / "home", root)
               if t.get("source") == "reviewer-finding"]
    assert len(tickets) == 2


def test_reviewer_finding_classes_documented_in_review_core() -> None:
    """Every REVIEWER_FINDING_CLASSES member must appear (backticked) in review-core.md
    so the reviewer-facing vocab and the miner allow-list (the SoT) cannot silently drift."""
    review_core = (
        Path(lm.__file__).resolve().parents[1]
        / "skills" / "adversarial-review-loop" / "references" / "review-core.md"
    ).read_text()
    missing = [c for c in lm.REVIEWER_FINDING_CLASSES if f"`{c}`" not in review_core]
    assert not missing, f"classes missing from review-core.md vocab list: {missing}"


def test_review_schema_class_accepts_any_value() -> None:
    """`class` must tolerate ANY value in review.schema — string, null, or a malformed
    non-string (number/array/object/bool) — so a reviewer typo can NEVER fail review.json
    validation and sink the whole review through the evidence gate's read_review. The vocab
    is enforced in the miner allow-list, not the schema. Regression-lock for the bug where a
    non-string class (`class: 42`) raised MalformedReviewError and dropped all findings."""
    import jsonschema  # noqa: PLC0415

    schema = json.loads(
        (Path(lm.__file__).resolve().parents[1] / "schemas" / "review.schema.json").read_text()
    )
    cls = schema["properties"]["findings"]["items"]["properties"]["class"]
    assert "enum" not in cls and "type" not in cls  # no constraint that could reject a value
    validator = jsonschema.Draft202012Validator(schema)

    def _review(class_val: object) -> dict:
        return {
            "schema_version": 1, "reviewer": "r", "contract_id": "c", "verdict": "REJECT",
            "scope_check": "PASS",
            "findings": [{"severity": "P1", "file": "a.py", "issue": "x", "class": class_val,
                          "fix": "y", "finding_hash": "a" * 64}],
            "verify_rerun": {"cmd": "x", "exit_code": 1},
            "reviewer_meta": {"model": "m", "started_at": "2026-06-17T00:00:00+00:00",
                              "ended_at": "2026-06-17T00:00:01+00:00"},
        }
    for val in ("null-deref", None, 42, ["x"], {"k": "v"}, True):
        validator.validate(_review(val))  # must not raise for ANY type


def test_reviewer_multi_file_glob_skips_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A multi-file reviewer glob with one unreadable path still processes the
    others — locks the shared `_iter_jsonl_dicts` per-path OSError semantics after
    the scan-loop extraction (one path's OSError must not abort the glob loop)."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": "r1"}))
    (d / "critic-rejections-phase-1.jsonl").write_text(
        json.dumps({"file": "a.py", "issue": "bug a", "run_id": "r1"}) + "\n")
    # phase-2 is a DIRECTORY → read_text() raises IsADirectoryError (OSError) → skipped.
    (d / "critic-rejections-phase-2.jsonl").mkdir()
    (d / "critic-rejections-phase-3.jsonl").write_text(
        json.dumps({"file": "c.py", "issue": "bug c", "run_id": "r1"}) + "\n")
    obs = lm.scan_reviewer_findings(root, "r1")
    assert sorted(o.file_basename for o in obs) == ["a.py", "c.py"]


def _run_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runs: list) -> dict:
    """Append findings across two runs to one repo's reviewer JSONL; return the
    last run_miner result. Each runs entry = (run_id, [finding-dict-without-run_id])."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    (root / ".planning" / "auto-pilot").mkdir(parents=True)
    state = root / ".planning/auto-pilot/state.json"
    jsonl = root / ".planning/auto-pilot/critic-rejections-phase-1.jsonl"
    res: dict = {}
    for run_id, finds in runs:
        state.write_text(json.dumps({"run_id": run_id}))
        with jsonl.open("a") as fh:
            for f in finds:
                fh.write(json.dumps({**f, "run_id": run_id}) + "\n")
        res = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    return res


def test_reviewer_empty_identity_findings_not_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two findings with neither a valid class NOR a non-empty issue (no defect
    identity) in the same file across two runs must NOT collapse into one
    falsely-promoting ticket. Pre-fix, both keyed on the constant empty fingerprint
    → distinct_runs reached 2 → false promotion (mirrors scan_insights empty guard)."""
    res = _run_two(tmp_path, monkeypatch, [
        ("r1", [{"file": "x.py", "issue": ""}]),
        ("r2", [{"file": "x.py", "issue": ""}]),
    ])
    assert res["verdict"] == "thin"
    assert res["promotable_count"] == 0
    tickets = [t for t in _ledger_tickets(tmp_path / "home", tmp_path / "repo")
               if t.get("source") == "reviewer-finding"]
    assert tickets == []  # empty-identity findings produce no ticket at all


def test_reviewer_class_variant_normalizes_and_collapses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A class with trailing space / different case must normalize to the canonical
    vocab member so the same defect still collapses to ONE promotable ticket. Pre-fix,
    exact membership rejected ` index-out-of-bounds `/`Index-Out-Of-Bounds` → fragmented."""
    res = _run_two(tmp_path, monkeypatch, [
        ("r1", [{"file": "m.py", "issue": "wording one", "class": "index-out-of-bounds"}]),
        ("r2", [{"file": "m.py", "issue": "wording two", "class": "Index-Out-Of-Bounds "}]),
    ])
    assert res["verdict"] == "promotable"
    tickets = [t for t in _ledger_tickets(tmp_path / "home", tmp_path / "repo")
               if t.get("source") == "reviewer-finding"]
    assert len(tickets) == 1
    assert tickets[0]["distinct_runs"] == 2
