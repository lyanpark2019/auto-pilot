"""tests/test_learning_miner.py — core scan/persist/dedup + lifecycle regression."""
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


def _planning(tmp_path: Path, run_id: str, findings: list[dict]) -> Path:
    d = tmp_path / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(
        json.dumps({"run_id": run_id, "pivot_detector": {}})
    )
    with (d / "critic-rejections-phase-1.jsonl").open("w") as f:
        for fi in findings:
            f.write(json.dumps(fi) + "\n")
    return tmp_path


def _ledger_tickets(home_root: Path, repo_root: Path) -> list[dict]:
    slug = str(repo_root.resolve()).replace("/", "-")
    d = home_root / ".claude" / "projects" / slug / "improvements"
    return [json.loads(Path(f).read_text()) for f in glob.glob(str(d / "*.json"))]


# --- scaffold note: the original test_reviewer_two_distinct_runs_promotable is
# INCOHERENT (two different repo roots → different slugs, never promotes).
# DELETED per plan self-review note. The real path is test_same_root_two_runs_promotable.


def test_same_root_two_runs_promotable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    (root / ".planning" / "auto-pilot").mkdir(parents=True)
    state = root / ".planning/auto-pilot/state.json"
    jsonl = root / ".planning/auto-pilot/critic-rejections-phase-1.jsonl"
    # run 1: the finding captured under run r1 (per-line run_id, as the producer stamps).
    state.write_text(json.dumps({"run_id": "r1"}))
    jsonl.write_text(json.dumps(
        {"file": "a.py", "issue": "missing token check", "candidate_asset": "hook", "run_id": "r1"}
    ) + "\n")
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"
    # run 2: the SAME finding recurs in a genuinely distinct run r2 — a NEW line
    # stamped with r2 (not a re-mine of the r1 line). distinct_runs -> 2 -> promotable.
    state.write_text(json.dumps({"run_id": "r2"}))
    with jsonl.open("a") as fh:
        fh.write(json.dumps(
            {"file": "a.py", "issue": "missing token check", "candidate_asset": "hook", "run_id": "r2"}
        ) + "\n")
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "promotable"


def test_legacy_no_run_id_line_not_inflated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A legacy line with no run_id must NOT inflate distinct_runs across mines.

    Pre-D2 the no-run_id line fell back to the live state run_id, so re-mining the
    same persisted line under a fresh state run_id climbed distinct_runs to 2 (false
    promotion). It now collapses to a single synthetic run -> stays thin forever.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    # No run_id key on the finding (legacy / agent-prose-written line).
    (d / "critic-rejections-phase-1.jsonl").write_text(
        json.dumps({"file": "a.py", "issue": "missing token check", "candidate_asset": "hook"}) + "\n"
    )
    (d / "state.json").write_text(json.dumps({"run_id": "r1"}))
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"
    # Flip the state run_id and re-mine the SAME persisted line — must stay thin.
    (d / "state.json").write_text(json.dumps({"run_id": "r2"}))
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"


def test_empty_inputs_thin_no_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    root.mkdir()
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"


def test_dry_run_verdict_matches_persist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    (root / ".planning/auto-pilot").mkdir(parents=True)
    (root / ".planning/auto-pilot/state.json").write_text(json.dumps({"run_id": "r1"}))
    (root / ".planning/auto-pilot/critic-rejections-phase-1.jsonl").write_text(
        json.dumps({"file": "a.py", "line": 1, "issue": "x", "candidate_asset": None}) + "\n"
    )
    dry = lm.run_miner(root, commit_to=None, now=NOW, dry_run=True)["verdict"]
    wet = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"]
    assert dry == wet


def test_fail_on_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    root.mkdir()
    assert lm.main(["--repo-root", str(root), "--fail-on", "promotable"]) == 0


def test_reviewer_finding_missing_issue_no_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": "r1"}))
    (d / "critic-rejections-phase-1.jsonl").write_text(json.dumps({"file": "a.py"}) + "\n")
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"


def test_reviewer_finding_out_of_enum_asset_coerced_not_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A candidate_asset outside the schema enum (e.g. a path) must coerce to
    None and still produce a ticket — never be silently dropped on ValidationError."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": "r1"}))
    (d / "critic-rejections-phase-1.jsonl").write_text(
        json.dumps({"file": "a.py", "issue": "bad thing", "candidate_asset": "hooks/foo.sh"})
        + "\n"
    )
    res = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert res["candidates"] == 1
    assert res["by_asset"] == {"none": 1}


def test_run_miner_skips_crashing_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": "r1"}))
    (d / "critic-rejections-phase-1.jsonl").write_text(
        json.dumps({"file": "a.py", "issue": "boom", "candidate_asset": "hook"}) + "\n"
    )

    def boom(*_a: object, **_k: object) -> dict[str, object]:
        raise RuntimeError("simulated")

    monkeypatch.setattr(lm.imp, "bump_or_create", boom)
    res = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert res["verdict"] == "thin" and res["candidates"] == 0


def test_doom_loop_cross_run_promotes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # pivot_detector is NESTED: {"phase-N": {"finding_hash": count}} per _state.py TypedDict.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    res = {"verdict": "thin"}
    for i, phase in enumerate(["phase-1", "phase-2", "phase-3"], start=1):
        (d / "state.json").write_text(
            json.dumps({"run_id": f"r{i}", "pivot_detector": {phase: {"hash-abc": 3}}})
        )
        res = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert res["verdict"] == "promotable"


def test_nested_pivot_detector_produces_doom_loop_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix 3: scan_doom_loops must handle the NESTED pivot_detector shape.

    The real writer (orchestrator.cmd_pivot_check) stores:
        pivot_detector = {"phase-N": {"finding_hash": count}}
    The old code iterated the outer dict and called int() on the inner dict
    (a TypeError), caught silently, so every doom-loop signal was dropped.

    This test proves:
      - A nested pivot_detector {"phase-1": {"abc": 3}} produces >=1 Observation
        (fails on old code → 0 observations; passes after fix).
      - The observation source is "doom-loop".
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    # Nested shape: single phase, single finding hash with count=3.
    nested = {"phase-1": {"abc123def": 3}}
    (d / "state.json").write_text(
        json.dumps({"run_id": "r1", "pivot_detector": nested})
    )
    observations = lm.scan_doom_loops(root, "r1")
    assert len(observations) >= 1, (
        f"Expected >=1 doom-loop Observation from nested pivot_detector, got {len(observations)}. "
        "Old code: int({{hash: count}}) raised TypeError → caught → DEAD signal."
    )
    assert all(o.source == "doom-loop" for o in observations)


def test_dry_run_creates_no_improvements_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": "r1"}))
    (d / "critic-rejections-phase-1.jsonl").write_text(
        json.dumps({"file": "a.py", "line": 1, "issue": "x", "candidate_asset": None}) + "\n"
    )
    lm.run_miner(root, commit_to=None, now=NOW, dry_run=True)
    led = lm.imp.ledger_dir(root, None)
    assert not led.exists()


def test_fail_on_exit_code_two_when_promotable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    # Genuine recurrence across two distinct runs (per-line run_id, as the producer stamps).
    base = {"file": "a.py", "issue": "missing token check", "candidate_asset": "hook"}
    (d / "critic-rejections-phase-1.jsonl").write_text(
        json.dumps({**base, "run_id": "r1"}) + "\n"
        + json.dumps({**base, "run_id": "r2"}) + "\n"
    )
    (d / "state.json").write_text(json.dumps({"run_id": "r2"}))
    assert lm.main(["--repo-root", str(root), "--fail-on", "promotable"]) == 2


def test_valid_asset_types_matches_schema_enum() -> None:
    """VALID_ASSET_TYPES must mirror the schema candidate_asset enum (no drift)."""
    schema = json.loads(lm.imp.SCHEMA_PATH.read_text())
    enum = schema["properties"]["candidate_asset"]["enum"]
    non_null = {e for e in enum if isinstance(e, str)}
    assert lm.VALID_ASSET_TYPES == non_null


# ---------------------------------------------------------------------------
# Full-lifecycle accumulation test: corrupt lines must not create phantom entries
# ---------------------------------------------------------------------------


def test_corrupt_insights_no_phantom_ledger_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression-lock: a corrupt/garbage insights.jsonl line must NOT create a
    phantom Hermes ledger entry and must NOT inflate distinct_runs.

    Lifecycle exercised end-to-end (scan → persist → dedup across two runs):
      - insights.jsonl seeded with 2 valid distinct classes + 4 corrupt variants
      - Run 1 (run_id="r1"): assert exactly 3 ledger tickets (2 class-keyed +
        1 issue-fallback), each distinct_runs==1
      - Run 2 (run_id="r2"): same insights re-scanned; assert still exactly 3
        tickets but each now distinct_runs==2 (dedup worked correctly)
      - Truly corrupt lines (garbage bytes, malformed JSON, empty {}, []) produce
        zero additional tickets across both runs.
      - The REAL ~/.claude/projects ledger is never written (writes go to a temp dir
        via monkeypatched HOME).
    """
    # Capture real home BEFORE patching, so we can prove no writes escaped there.
    real_home = Path.home()
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))

    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)

    # Two distinct valid insight classes.
    valid_a = {"class": "fail-open-guard", "issue": "guard fails open on compound cmd", "candidate_asset": "hook"}
    valid_b = {"class": "missing-test-coverage", "issue": "no test for error path", "candidate_asset": "test"}

    # Corrupt variants: each must be silently skipped.
    # Note: the "orphan issue" line has no "class" key but a non-empty "issue" — the
    # miner falls back to the issue text, producing a THIRD valid ticket.  This is
    # intentional: we want to confirm the fallback path also works correctly AND that
    # its ticket is separate from valid_a / valid_b (distinct_runs not shared).
    corrupt_lines = [
        "this is not json at all !!!",               # garbage bytes
        "{not valid json",                            # malformed JSON
        "{}",                                         # empty object (no class, no issue → skipped)
        "[]",                                         # JSON array (not a dict → skipped)
        json.dumps({"issue": "orphan issue no class key present", "candidate_asset": "hook"}),
    ]

    def _write_insights(run_id: str) -> None:
        (d / "state.json").write_text(json.dumps({"run_id": run_id}))
        with (d / "insights.jsonl").open("w") as f:
            f.write(json.dumps(valid_a) + "\n")
            f.write(json.dumps(valid_b) + "\n")
            for corrupt in corrupt_lines:
                f.write(corrupt + "\n")

    # --- Run 1 ---
    _write_insights("r1")
    result_r1 = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)

    tickets_r1 = _ledger_tickets(fake_home, root)

    # valid_a, valid_b, plus orphan-issue fallback = 3 valid observations.
    # The 4 truly corrupt lines (garbage, malformed JSON, {}, []) produce 0 tickets.
    assert result_r1["candidates"] == 3, (
        f"run-1 candidates mismatch: expected 3, got {result_r1['candidates']}"
    )
    assert len(tickets_r1) == 3, (
        f"run-1 ledger ticket count: expected 3 files, got {len(tickets_r1)}"
    )

    # Each ticket must have distinct_runs == 1 (first observation only).
    for t in tickets_r1:
        assert t["distinct_runs"] == 1, (
            f"run-1 ticket {t.get('fingerprint','?')[:8]} distinct_runs={t['distinct_runs']}, expected 1"
        )

    # Extra paranoia: none of the tickets should have a pattern matching raw corrupt
    # content (those lines were never parsed into observations at all).
    all_patterns = {t.get("pattern", "") for t in tickets_r1}
    for impossible in ("this is not json at all !!!", "{not valid json"):
        assert impossible not in all_patterns, (
            f"Corrupt line leaked into ticket pattern: {impossible!r}"
        )

    # --- Run 2: same insights, new run_id ---
    _write_insights("r2")
    result_r2 = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    tickets_r2 = _ledger_tickets(fake_home, root)

    assert result_r2["candidates"] == 3, (
        f"run-2 candidates mismatch: expected 3, got {result_r2['candidates']}"
    )
    assert len(tickets_r2) == 3, (
        f"run-2 ledger ticket count: expected still 3 (no new phantom), got {len(tickets_r2)}"
    )

    # Each ticket must now have distinct_runs == 2 (dedup worked, not inflated by corrupt lines).
    for t in tickets_r2:
        assert t["distinct_runs"] == 2, (
            f"run-2 ticket {t.get('fingerprint','?')[:8]} distinct_runs={t['distinct_runs']}, expected 2"
        )

    # --- Confirm the REAL home ledger was NOT touched ---
    # We use the REAL home captured before monkeypatching.  If any write escaped
    # the HOME patch it would appear here.
    slug = str(root.resolve()).replace("/", "-")
    real_slug_dir = real_home / ".claude" / "projects" / slug / "improvements"
    assert not real_slug_dir.exists(), (
        f"REAL home ledger was written to: {real_slug_dir}"
    )

    # All writes must be under fake_home only.
    fake_slug_dir = fake_home / ".claude" / "projects" / slug / "improvements"
    assert fake_slug_dir.exists(), "Expected writes under fake_home, but dir not found"
