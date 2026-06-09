"""tests/test_learning_miner.py — TDD for learning_miner (Task 3)."""
from __future__ import annotations

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
