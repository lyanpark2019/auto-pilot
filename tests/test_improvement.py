import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import _improvement as imp  # noqa: E402
from _improvement import Observation  # noqa: E402

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "improvement-ticket.schema.json"
NOW = datetime(2026, 6, 9, tzinfo=timezone.utc)


def _valid_ticket():
    return {
        "schema_version": 1,
        "fingerprint": "a" * 64,
        "state": "candidate",
        "pattern": "missing verify evidence",
        "source": "reviewer-finding",
        "candidate_asset": "hook",
        "occurrences": 1,
        "distinct_runs": 1,
        "first_seen": "2026-06-09T00:00:00Z",
        "last_seen": "2026-06-09T00:00:00Z",
        "plugin_version": "0.8.7",
        "repo_fingerprint": "abc123",
        "evidence": [{"run_id": "r1", "snippet": "reviewer said X"}],
        "promotion_gate": {"tests_pass": None, "ci_pass": None, "user_approved": None},
    }


def _validate(obj):
    imp.validate_ticket(obj)


def test_valid_ticket_passes():
    _validate(_valid_ticket())


def test_extra_property_rejected():
    import jsonschema

    t = _valid_ticket()
    t["bogus"] = 1
    with pytest.raises(jsonschema.ValidationError):
        _validate(t)


def test_bad_state_rejected():
    import jsonschema

    t = _valid_ticket()
    t["state"] = "nope"
    with pytest.raises(jsonschema.ValidationError):
        _validate(t)


def test_short_fingerprint_rejected():
    import jsonschema

    t = _valid_ticket()
    t["fingerprint"] = "abc"
    with pytest.raises(jsonschema.ValidationError):
        _validate(t)


def test_empty_evidence_rejected():
    import jsonschema

    t = _valid_ticket()
    t["evidence"] = []
    with pytest.raises(jsonschema.ValidationError):
        _validate(t)


def test_fingerprint_stable_across_line_path_date():
    a = imp.compute_fingerprint(
        "reviewer-finding",
        "auth.py",
        "phase-2 /Users/x/auth.py:88 missing token check 2026-06-09",
        "hook",
    )
    b = imp.compute_fingerprint(
        "reviewer-finding",
        "auth.py",
        "phase-5 /tmp/auth.py:120 missing token check 2026-01-01",
        "hook",
    )
    assert a == b


def test_fingerprint_distinguishes_semantics():
    a = imp.compute_fingerprint("reviewer-finding", "a.py", "missing token check", "hook")
    b = imp.compute_fingerprint(
        "reviewer-finding", "a.py", "unbounded recursion in parser", "hook"
    )
    assert a != b


def test_bump_new_run_increments_distinct(tmp_path):
    obs1 = Observation("reviewer-finding", "a.py", "missing token check", "hook", "r1", "snip-a")
    obs2 = Observation("reviewer-finding", "a.py", "missing token check", "hook", "r2", "snip-b")
    imp.bump_or_create(tmp_path, obs1, repo_root=tmp_path, now=NOW, dry_run=False)
    t2 = imp.bump_or_create(tmp_path, obs2, repo_root=tmp_path, now=NOW, dry_run=False)
    assert t2["occurrences"] == 2 and t2["distinct_runs"] == 2


def test_same_run_retrip_keeps_distinct_one(tmp_path):
    obs1 = Observation("reviewer-finding", "a.py", "missing token check", "hook", "r1", "snip-a")
    obs2 = Observation("reviewer-finding", "a.py", "missing token check", "hook", "r1", "snip-b")
    imp.bump_or_create(tmp_path, obs1, repo_root=tmp_path, now=NOW, dry_run=False)
    t = imp.bump_or_create(tmp_path, obs2, repo_root=tmp_path, now=NOW, dry_run=False)
    assert t["occurrences"] == 2 and t["distinct_runs"] == 1


def test_rescan_is_idempotent(tmp_path):
    obs = Observation("reviewer-finding", "a.py", "missing token check", "hook", "r1", "snip-a")
    imp.bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)
    t = imp.bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)
    assert t["occurrences"] == 1 and t["distinct_runs"] == 1


def test_dry_run_writes_nothing(tmp_path):
    obs = Observation("reviewer-finding", "a.py", "x issue", "hook", "r1", "snip")
    imp.bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=True)
    assert list(tmp_path.glob("*.json")) == []


def test_bumped_ticket_is_schema_valid(tmp_path):
    obs = Observation("reviewer-finding", "a.py", "missing token check", "hook", "r1", "snip")
    t = imp.bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)
    imp.validate_ticket(t)


def test_parallel_bump_no_lost_update(tmp_path):
    import concurrent.futures as cf

    def one(i):
        obs = Observation(
            "reviewer-finding", "a.py", "missing token check", "hook", f"r{i}", f"s{i}"
        )
        return imp.bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(one, range(8)))
    import json

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    t = json.loads(files[0].read_text())
    assert t["distinct_runs"] == 8


def test_repo_fingerprint_from_repo_root_not_ledger(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    led = tmp_path / "led"
    led.mkdir()
    obs = Observation("reviewer-finding", "a.py", "x", "hook", "r1", "s")
    t = imp.bump_or_create(led, obs, repo_root=root, now=NOW, dry_run=False)
    assert t["repo_fingerprint"] == imp.repo_fingerprint(root)
    assert t["repo_fingerprint"] != imp.repo_fingerprint(led)


def test_malformed_existing_ticket_recovers(tmp_path):
    obs = Observation("reviewer-finding", "a.py", "missing token check", "hook", "r1", "s")
    fp = imp.compute_fingerprint("reviewer-finding", "a.py", "missing token check", "hook")
    (tmp_path / f"{fp}.json").write_text("{not valid json")
    t = imp.bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)
    assert t["occurrences"] == 1 and t["distinct_runs"] == 1
    imp.validate_ticket(t)


def test_dry_run_creates_no_ledger_dir(tmp_path):
    led = tmp_path / "does-not-exist"
    obs = Observation("reviewer-finding", "a.py", "x", "hook", "r1", "s")
    imp.bump_or_create(led, obs, repo_root=tmp_path, now=NOW, dry_run=True)
    assert not led.exists()


def test_normalize_strips_iso_offset():
    a = imp.compute_fingerprint("s", "f", "done at 2026-06-09T12:00:00Z ok", "hook")
    b = imp.compute_fingerprint("s", "f", "done at 2026-06-09T12:00:00+00:00 ok", "hook")
    c = imp.compute_fingerprint("s", "f", "done at 2026-01-01T03:30:00-05:00 ok", "hook")
    assert a == b == c


@pytest.mark.parametrize(
    "corrupt",
    ['{}', '{"evidence": [{"bad": 1}]}', '{"state": "candidate", "evidence": []}'],
)
def test_schema_invalid_existing_ticket_reseeds(tmp_path, corrupt):
    obs = Observation("reviewer-finding", "a.py", "missing token check", "hook", "r1", "s")
    fp = imp.compute_fingerprint("reviewer-finding", "a.py", "missing token check", "hook")
    (tmp_path / f"{fp}.json").write_text(corrupt)
    t = imp.bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)
    assert t["occurrences"] == 1 and t["distinct_runs"] == 1
    imp.validate_ticket(t)


@pytest.mark.parametrize("issue", ["", "   ", "src/auth.py", "phase-3", ":42"])
def test_empty_normalized_issue_does_not_crash(tmp_path, issue):
    obs = Observation("reviewer-finding", "", issue, None, "r1", "s")
    t = imp.bump_or_create(tmp_path, obs, repo_root=tmp_path, now=NOW, dry_run=False)
    imp.validate_ticket(t)
    assert t["pattern"]


def test_repo_fingerprint_refreshed_on_rebump(tmp_path):
    obs1 = Observation("reviewer-finding", "a.py", "x", "hook", "r1", "s1")
    fp = imp.compute_fingerprint("reviewer-finding", "a.py", "x", "hook")
    imp.bump_or_create(tmp_path, obs1, repo_root=tmp_path, now=NOW, dry_run=False)
    p = tmp_path / f"{fp}.json"
    d = json.loads(p.read_text())
    d["repo_fingerprint"] = "stalexxxxxxxxxx"
    p.write_text(json.dumps(d))
    obs2 = Observation("reviewer-finding", "a.py", "x", "hook", "r2", "s2")
    t = imp.bump_or_create(tmp_path, obs2, repo_root=tmp_path, now=NOW, dry_run=False)
    assert t["repo_fingerprint"] == imp.repo_fingerprint(tmp_path)
