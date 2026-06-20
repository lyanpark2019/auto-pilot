"""Tests for scripts/_escalation_seed.py — deterministic seed harness.

Covers: exact distribution, schema validity, distinct fingerprints,
byte-stability, source-check (no datetime.now/random), and a real-CLI
subprocess round-trip (seed → measure-escalation → assert expected metrics).
"""
from __future__ import annotations

import inspect
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _escalation_seed as seed_mod  # noqa: E402
from _escalation import validate_escalation  # noqa: E402
from _escalation_seed import build_seed_records, _write_records  # noqa: E402

NOW = datetime(2026, 6, 15, tzinfo=timezone.utc)
NOW_STR = "2026-06-15T00:00:00Z"


# ---------------------------------------------------------------------------
# 1. Exact distribution: state split
# ---------------------------------------------------------------------------


class TestExactDistribution:
    def test_state_split_exact(self) -> None:
        """count=10, resolved=4, abandoned=3, enriched=1 → open=2."""
        records = build_seed_records(
            count=10, resolved=4, abandoned=3, enriched=1, now=NOW
        )
        by_state = {}
        for r in records:
            s = r["state"]
            by_state[s] = by_state.get(s, 0) + 1

        assert by_state.get("resolved", 0) == 4
        assert by_state.get("abandoned", 0) == 3
        assert by_state.get("enriched", 0) == 1
        assert by_state.get("open", 0) == 2
        assert sum(by_state.values()) == 10

    def test_all_open(self) -> None:
        records = build_seed_records(count=5, resolved=0, abandoned=0, enriched=0, now=NOW)
        for r in records:
            assert r["state"] == "open"

    def test_all_resolved(self) -> None:
        records = build_seed_records(count=3, resolved=3, abandoned=0, enriched=0, now=NOW)
        for r in records:
            assert r["state"] == "resolved"

    def test_sum_exceeds_count_raises(self) -> None:
        import pytest  # noqa: PLC0415

        with pytest.raises(ValueError, match="count"):
            build_seed_records(count=5, resolved=3, abandoned=3, enriched=0, now=NOW)

    def test_zero_count_raises(self) -> None:
        import pytest  # noqa: PLC0415

        with pytest.raises(ValueError, match="count"):
            build_seed_records(count=0, resolved=0, abandoned=0, enriched=0, now=NOW)


# ---------------------------------------------------------------------------
# 2. Schema validity: every built record passes validate_escalation
# ---------------------------------------------------------------------------


class TestSchemaValidity:
    def test_all_records_valid(self) -> None:
        records = build_seed_records(
            count=7, resolved=2, abandoned=2, enriched=1, now=NOW
        )
        for r in records:
            validate_escalation(r)  # raises jsonschema.ValidationError on failure

    def test_enriched_has_enrichment_block(self) -> None:
        records = build_seed_records(count=5, resolved=0, abandoned=0, enriched=2, now=NOW)
        enriched = [r for r in records if r["state"] == "enriched"]
        assert len(enriched) == 2
        for r in enriched:
            assert "enrichment" in r
            counts = r["enrichment"]["counts"]
            assert "admitted" in counts and "rejected" in counts

    def test_resolved_has_resolved_at(self) -> None:
        records = build_seed_records(count=4, resolved=2, abandoned=0, enriched=0, now=NOW)
        resolved = [r for r in records if r["state"] == "resolved"]
        assert len(resolved) == 2
        for r in resolved:
            assert "resolved_at" in r

    def test_abandoned_has_resolved_at(self) -> None:
        records = build_seed_records(count=3, resolved=0, abandoned=2, enriched=0, now=NOW)
        abandoned = [r for r in records if r["state"] == "abandoned"]
        assert len(abandoned) == 2
        for r in abandoned:
            assert "resolved_at" in r


# ---------------------------------------------------------------------------
# 3. Distinct fingerprints — no collision
# ---------------------------------------------------------------------------


class TestDistinctFingerprints:
    def test_all_fingerprints_unique(self) -> None:
        records = build_seed_records(count=20, resolved=5, abandoned=3, enriched=2, now=NOW)
        fps = [r["fingerprint"] for r in records]
        assert len(fps) == len(set(fps)), f"fingerprint collisions detected: {fps}"

    def test_fingerprint_length_64(self) -> None:
        records = build_seed_records(count=3, resolved=0, abandoned=0, enriched=0, now=NOW)
        for r in records:
            assert len(r["fingerprint"]) == 64


# ---------------------------------------------------------------------------
# 4. Byte-stability: same now → identical output
# ---------------------------------------------------------------------------


class TestByteStability:
    def test_same_now_identical_output(self) -> None:
        r1 = build_seed_records(count=8, resolved=3, abandoned=2, enriched=1, now=NOW)
        r2 = build_seed_records(count=8, resolved=3, abandoned=2, enriched=1, now=NOW)
        assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)

    def test_no_datetime_now_in_build(self) -> None:
        src = inspect.getsource(build_seed_records)
        assert "datetime.now" not in src, "build_seed_records must not call datetime.now"
        assert "date.today" not in src, "build_seed_records must not call date.today"

    def test_no_random_in_build(self) -> None:
        src = inspect.getsource(build_seed_records)
        assert "random" not in src, "build_seed_records must not call random"

    def test_no_datetime_now_in_module(self) -> None:
        """Full module source must have no datetime.now / random outside cmd_* handlers."""
        # We check the module-level functions that must be pure:
        for fn_name in ("build_seed_records", "_write_records"):
            fn = getattr(seed_mod, fn_name, None)
            if fn is None:
                continue
            fn_src = inspect.getsource(fn)
            assert "datetime.now" not in fn_src, f"{fn_name} must not call datetime.now"
            assert "random" not in fn_src, f"{fn_name} must not call random"


# ---------------------------------------------------------------------------
# 5. _write_records: disk round-trip
# ---------------------------------------------------------------------------


class TestWriteRecords:
    def test_writes_returns_count(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """_write_records returns the count of records passed in."""
        monkeypatch.setenv("HOME", str(tmp_path))
        records = build_seed_records(count=5, resolved=2, abandoned=1, enriched=0, now=NOW)
        n = _write_records(records, tmp_path)
        assert n == 5

    def test_written_records_are_valid_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Records written to disk are schema-valid JSON.

        Computes the ledger path directly via project_slug (bypasses any leaked
        ledger_dir mock from concurrent-mock teardown in test_escalation_resolution.py).
        """
        monkeypatch.setenv("HOME", str(tmp_path))
        records = build_seed_records(count=3, resolved=1, abandoned=1, enriched=0, now=NOW)
        from _escalation import validate_escalation  # noqa: PLC0415
        from _identity import project_slug  # noqa: PLC0415

        # Compute ledger path without going through ledger_dir (which may be mocked).
        slug = project_slug(tmp_path)
        led = tmp_path / ".claude" / "projects" / slug / "escalations"

        _write_records(records, tmp_path)
        for record in records:
            fp = record["fingerprint"]
            path = led / f"{fp}.json"
            assert path.exists(), f"expected {path} to exist (led={led})"
            obj = json.loads(path.read_text())
            validate_escalation(obj)


# ---------------------------------------------------------------------------
# 6. Custom problem_classes round-robin
# ---------------------------------------------------------------------------


class TestProblemClassSpread:
    def test_custom_classes_round_robin(self) -> None:
        classes = ["doom-loop", "unknown-library"]
        records = build_seed_records(
            count=6, resolved=0, abandoned=0, enriched=0, now=NOW, problem_classes=classes
        )
        pc_list = [r["problem_class"] for r in records]
        # Round-robin: alternates doom-loop, unknown-library, doom-loop, ...
        expected = [classes[i % 2] for i in range(6)]
        assert pc_list == expected

    def test_default_classes_spread(self) -> None:
        """Default _PROBLEM_CLASS_CHOICES spread over 14 records covers all 7 twice."""
        from _escalation import _PROBLEM_CLASS_CHOICES  # noqa: PLC0415

        records = build_seed_records(
            count=14, resolved=0, abandoned=0, enriched=0, now=NOW
        )
        seen = {r["problem_class"] for r in records}
        assert seen == set(_PROBLEM_CLASS_CHOICES)


# ---------------------------------------------------------------------------
# 7. Real CLI subprocess round-trip: seed → measure-escalation
# ---------------------------------------------------------------------------


def test_cli_seed_then_measure(tmp_path: Path) -> None:
    """seed --count=10 --resolved-pct=40 → measure-escalation → total=10, recovery_rate=40.0."""
    import os as _os  # noqa: PLC0415
    import site as _site  # noqa: PLC0415

    scripts_dir = ROOT / "scripts"

    # Isolate the HOME ledger so this test never writes to the real
    # ~/.claude/projects/ store.  Both seed and measure must share the same
    # fake HOME so they operate on the same ledger namespace.
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    user_site = _site.getusersitepackages()
    existing_pp = _os.environ.get("PYTHONPATH", "")
    pythonpath = _os.pathsep.join(
        p for p in [existing_pp, user_site, str(scripts_dir)] if p
    )
    env = {**_os.environ, "HOME": str(fake_home), "PYTHONPATH": pythonpath}

    # Seed 10 records: 40% resolved = 4, 30% abandoned = 3, 10% enriched = 1, open = 2
    r_seed = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "escalation-seed",
            "--repo-root", str(tmp_path),
            "--count", "10",
            "--resolved-pct", "40",
            "--abandoned-pct", "30",
            "--enriched-pct", "10",
            "--now", NOW_STR,
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
        env=env,
    )
    assert r_seed.returncode == 0, (
        f"escalation-seed failed:\nstdout={r_seed.stdout}\nstderr={r_seed.stderr}"
    )
    seed_out = json.loads(r_seed.stdout.strip())
    assert seed_out["count"] == 10
    assert seed_out["written"] == 10
    assert seed_out["by_state"]["resolved"] == 4
    assert seed_out["by_state"]["abandoned"] == 3

    # Now measure — same fake HOME so the ledger path resolves identically.
    r_meas = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "measure-escalation",
            "--repo-root", str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
        env=env,
    )
    assert r_meas.returncode == 0, (
        f"measure-escalation failed:\nstdout={r_meas.stdout}\nstderr={r_meas.stderr}"
    )
    meas = json.loads(r_meas.stdout.strip())
    assert meas["total"] == 10, f"expected total=10, got {meas['total']}"
    assert meas["by_state"]["resolved"] == 4
    assert meas["by_state"]["abandoned"] == 3
    assert meas["by_state"]["enriched"] == 1
    assert meas["by_state"]["open"] == 2
    # 4 resolved / 10 total = 40.0
    assert meas["recovery_rate_pct"] == 40.0, (
        f"expected recovery_rate_pct=40.0, got {meas['recovery_rate_pct']}"
    )
    # 4 resolved / (4+3) terminal = 57.1
    assert meas["resolution_rate_pct"] == 57.1, (
        f"expected resolution_rate_pct=57.1, got {meas['resolution_rate_pct']}"
    )


def test_cli_seed_dry_run_no_writes(tmp_path: Path) -> None:
    """--dry-run must print summary but write no files."""
    scripts_dir = ROOT / "scripts"
    import os as _os  # noqa: PLC0415
    import site as _site  # noqa: PLC0415

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    user_site = _site.getusersitepackages()
    pythonpath = _os.pathsep.join(
        p for p in [_os.environ.get("PYTHONPATH", ""), user_site, str(scripts_dir)] if p
    )
    env = {**_os.environ, "HOME": str(fake_home), "PYTHONPATH": pythonpath}

    r = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "escalation-seed",
            "--repo-root", str(tmp_path),
            "--count", "5",
            "--resolved-pct", "40",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
        env=env,
    )
    assert r.returncode == 0, f"seed --dry-run failed:\n{r.stderr}"
    out = json.loads(r.stdout.strip())
    assert out["count"] == 5
    assert out["written"] == 0

    # Under the fake HOME, no escalation ledger should have been created.
    assert not (fake_home / ".claude").exists(), (
        "dry-run must not create any escalation dirs under HOME"
    )
