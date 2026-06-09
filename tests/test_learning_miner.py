"""tests/test_learning_miner.py — TDD for learning_miner (Task 3)."""
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


# --- scaffold note: the original test_reviewer_two_distinct_runs_promotable is
# INCOHERENT (two different repo roots → different slugs, never promotes).
# DELETED per plan self-review note. The real path is test_same_root_two_runs_promotable.


def test_same_root_two_runs_promotable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    f = [{"file": "a.py", "line": 10, "issue": "missing token check", "candidate_asset": "hook"}]
    # run 1
    (root / ".planning" / "auto-pilot").mkdir(parents=True)
    (root / ".planning/auto-pilot/state.json").write_text(json.dumps({"run_id": "r1"}))
    (root / ".planning/auto-pilot/critic-rejections-phase-1.jsonl").write_text(
        json.dumps(f[0]) + "\n"
    )
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"
    # run 2 (new run_id, same finding)
    (root / ".planning/auto-pilot/state.json").write_text(json.dumps({"run_id": "r2"}))
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "promotable"


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
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    d = root / ".planning" / "auto-pilot"
    d.mkdir(parents=True)
    res = {"verdict": "thin"}
    for i, phase in enumerate(["phase-1", "phase-2", "phase-3"], start=1):
        (d / "state.json").write_text(
            json.dumps({"run_id": f"r{i}", "pivot_detector": {phase: 3}})
        )
        res = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert res["verdict"] == "promotable"


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
    finding = {"file": "a.py", "line": 1, "issue": "missing token check", "candidate_asset": "hook"}
    (d / "critic-rejections-phase-1.jsonl").write_text(json.dumps(finding) + "\n")
    (d / "state.json").write_text(json.dumps({"run_id": "r1"}))
    lm.main(["--repo-root", str(root)])
    (d / "state.json").write_text(json.dumps({"run_id": "r2"}))
    assert lm.main(["--repo-root", str(root), "--fail-on", "promotable"]) == 2


def test_valid_asset_types_matches_schema_enum() -> None:
    """VALID_ASSET_TYPES must mirror the schema candidate_asset enum (no drift)."""
    schema = json.loads(lm.imp.SCHEMA_PATH.read_text())
    enum = schema["properties"]["candidate_asset"]["enum"]
    non_null = {e for e in enum if isinstance(e, str)}
    assert lm.VALID_ASSET_TYPES == non_null


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
