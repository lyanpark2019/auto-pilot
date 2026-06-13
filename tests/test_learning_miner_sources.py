"""tests/test_learning_miner_sources.py — per-source-variant, promotion-threshold, run_id-guard cases."""
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


def _write_insights(root: Path, run_id: str, lines: list[dict]) -> None:
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({"run_id": run_id}))
    with (d / "insights.jsonl").open("w") as f:
        for ln in lines:
            f.write(json.dumps(ln) + "\n")


def _ledger_tickets(home_root: Path, repo_root: Path) -> list[dict]:
    slug = str(repo_root.resolve()).replace("/", "-")
    d = home_root / ".claude" / "projects" / slug / "improvements"
    return [json.loads(Path(f).read_text()) for f in glob.glob(str(d / "*.json"))]


def test_scan_insights_class_keyed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    _write_insights(
        root, "r1",
        [{"class": "fail-open", "issue": "guard fails open on compound cmd", "candidate_asset": "hook"}],
    )
    obs = lm.scan_insights(root, "r1")
    assert len(obs) == 1
    o = obs[0]
    assert o.source == "insight"
    assert o.file_basename == ""
    assert o.issue == "fail-open"
    assert o.candidate_asset == "hook"


def test_insight_promotes_at_3_distinct_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    line = {"class": "fail-open", "issue": "x", "candidate_asset": "hook"}
    _write_insights(root, "r1", [line])
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"
    _write_insights(root, "r2", [line])
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"
    _write_insights(root, "r3", [line])
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "promotable"


def test_insight_class_key_defragments_wording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    _write_insights(
        root, "r1",
        [
            {"class": "fail-open", "issue": "guard A fails open via option reorder", "candidate_asset": "hook"},
            {"class": "fail-open", "issue": "guard B fails open via push-first chain", "candidate_asset": "hook"},
        ],
    )
    lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    tickets = _ledger_tickets(tmp_path / "home", root)
    assert len(tickets) == 1  # same class, different wording → ONE ticket
    assert tickets[0]["occurrences"] == 2
    assert tickets[0]["distinct_runs"] == 1


def test_insight_missing_class_falls_back_to_issue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    _write_insights(root, "r1", [{"issue": "no class present here", "candidate_asset": "doc"}])
    obs = lm.scan_insights(root, "r1")
    assert len(obs) == 1
    assert obs[0].issue == "no class present here"


def test_insight_path_shaped_class_skipped_not_collapsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path/date-shaped class normalizes to '' → keying on it would collapse
    unrelated insights into one ticket. Such tags must be SKIPPED, not merged."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    _write_insights(
        root, "r1",
        [
            {"class": "hooks/foo.sh", "issue": "a", "candidate_asset": "hook"},
            {"class": "src/bar.ts", "issue": "b", "candidate_asset": "test"},
            {"class": "2026-06-09", "issue": "c", "candidate_asset": "doc"},
        ],
    )
    obs = lm.scan_insights(root, "r1")
    assert obs == []  # all three normalize to empty → skipped, never collapsed
    lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert _ledger_tickets(tmp_path / "home", root) == []


def test_insight_malformed_and_out_of_enum_tolerated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    _write_insights(
        root, "r1",
        [{"class": "race", "issue": "x", "candidate_asset": "hooks/foo.sh"}],
    )
    with (root / ".planning/auto-pilot/insights.jsonl").open("a") as f:
        f.write("not json at all\n{}\n[]\n")
    res = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert res["candidates"] >= 1  # tolerated, no crash
    tickets = _ledger_tickets(tmp_path / "home", root)
    race = [t for t in tickets if t["pattern"] == "race"]
    assert race and race[0]["candidate_asset"] is None  # out-of-enum coerced


# --- run_id guard cases ---


def test_empty_run_id_does_not_persist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With run_id=="" the miner must NOT write any ticket file to the ledger."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    line = {"class": "fail-open", "issue": "x", "candidate_asset": "hook"}

    # Case 1: run_id key present but empty string
    _write_insights(root, "", [line])
    result = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert "verdict" in result
    assert _ledger_tickets(tmp_path / "home", root) == []

    # Case 2: run_id key absent entirely from state.json
    d = root / ".planning" / "auto-pilot"
    (d / "state.json").write_text(json.dumps({}))
    result2 = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert "verdict" in result2
    assert _ledger_tickets(tmp_path / "home", root) == []


def test_empty_run_id_reports_projected_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty run_id: projection still visible (candidates == 1), not zeroed."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    line = {"class": "fail-open", "issue": "x", "candidate_asset": "hook"}
    _write_insights(root, "", [line])
    result = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert result["candidates"] == 1


def test_nonempty_run_id_still_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: non-empty run_id must still persist exactly one ticket."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    line = {"class": "fail-open", "issue": "x", "candidate_asset": "hook"}
    _write_insights(root, "r1", [line])
    lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert len(_ledger_tickets(tmp_path / "home", root)) == 1


def test_whitespace_run_id_does_not_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A whitespace-only run_id must be treated as empty — no ticket persisted."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    line = {"class": "fail-open", "issue": "x", "candidate_asset": "hook"}
    _write_insights(root, "   ", [line])
    lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert _ledger_tickets(tmp_path / "home", root) == []


def test_null_run_id_does_not_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JSON null run_id must not persist — str(null) == 'None' is truthy but invalid."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": None}))
    (d / "insights.jsonl").write_text(
        json.dumps({"class": "fail-open", "issue": "x", "candidate_asset": "hook"}) + "\n"
    )
    lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert _ledger_tickets(tmp_path / "home", root) == []


@pytest.mark.parametrize("payload", ["5", "[]", '"r1"', "null"])
def test_nondict_state_json_does_not_crash(tmp_path: Path, payload: str) -> None:
    """A non-dict state.json (JSON scalar/array) must yield '' not AttributeError."""
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(payload)
    assert lm.current_run_id(root) == ""


def test_promotion_thresholds_matches_source_enum() -> None:
    """PROMOTION_THRESHOLDS keys must mirror the schema source enum (no drift).

    A source added to the schema but not here would silently never promote
    (PROMOTION_THRESHOLDS.get(...) -> None); a key here absent from the schema
    is dead config.
    """
    schema = json.loads(lm.imp.SCHEMA_PATH.read_text())
    enum = set(schema["properties"]["source"]["enum"])
    assert set(lm.PROMOTION_THRESHOLDS) == enum


def test_numeric_run_id_does_not_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Numeric run_id 0 must not persist — str(0) == '0' is truthy but invalid."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": 0}))
    (d / "insights.jsonl").write_text(
        json.dumps({"class": "fail-open", "issue": "x", "candidate_asset": "hook"}) + "\n"
    )
    lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert _ledger_tickets(tmp_path / "home", root) == []
