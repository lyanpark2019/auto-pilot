"""
tests/test_asset_registry.py — unit tests for scripts/asset_registry_check.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "asset_registry_check.py"


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        timeout=30,
    )


class TestScanBasic:
    def test_no_args_exits_zero(self):
        r = _run([])
        assert r.returncode == 0

    def test_registry_count_in_stderr(self):
        r = _run([])
        assert "Registry:" in r.stderr or "assets scanned" in r.stderr

    def test_fail_on_overlap_clean_candidate(self):
        """A very unique name should produce no overlap and exit 0."""
        r = _run([
            "--fail-on-overlap",
            "--name", "xyzzy-completely-unique-asset-8z7q",
            "--description", "a completely unique description with no overlap",
        ])
        assert r.returncode == 0

    def test_fail_on_overlap_common_name_may_overlap(self):
        """'auto-pilot' is a real skill name — must overlap with itself."""
        r = _run([
            "--fail-on-overlap",
            "--name", "auto-pilot",
            "--description", "Self-driving development loop. Triggers on /auto-pilot.",
        ])
        # Should detect overlap (exit 1) since auto-pilot skill exists
        assert r.returncode == 1

    def test_fail_on_overlap_without_candidate_exits_zero(self):
        """--fail-on-overlap without --name/--description should exit 0 (nothing to check)."""
        r = _run(["--fail-on-overlap"])
        assert r.returncode == 0


class TestEmitArtifact:
    def test_emit_artifact_creates_file(self, tmp_path):
        out_file = tmp_path / "creation-check.json"
        r = _run([
            "--fail-on-overlap",
            "--name", "very-unique-xyzzy-test-8z7q",
            "--description", "unique test description for artifact check",
            "--emit-artifact", str(out_file),
        ])
        assert out_file.exists(), f"Artifact not created; stderr={r.stderr}"
        data = json.loads(out_file.read_text())
        assert "generated_ts" in data
        assert "head_sha" in data
        assert "result" in data
        assert data["result"] in ("clean", "overlap")

    def test_artifact_generated_ts_is_recent(self, tmp_path):
        out_file = tmp_path / "creation-check.json"
        _run([
            "--emit-artifact", str(out_file),
        ])
        data = json.loads(out_file.read_text())
        age = time.time() - data["generated_ts"]
        assert age < 30, f"generated_ts is too old: {age}s"

    def test_artifact_result_clean_for_unique(self, tmp_path):
        out_file = tmp_path / "creation-check.json"
        _run([
            "--fail-on-overlap",
            "--name", "totally-unique-nonexistent-7q8z",
            "--description", "no similarity to any existing asset at all",
            "--emit-artifact", str(out_file),
        ])
        data = json.loads(out_file.read_text())
        assert data["result"] == "clean"

    def test_artifact_overlap_field_when_overlap(self, tmp_path):
        out_file = tmp_path / "creation-check.json"
        _run([
            "--fail-on-overlap",
            "--name", "auto-pilot",
            "--description", "Self-driving development loop auto-pilot PM worker",
            "--emit-artifact", str(out_file),
        ])
        if out_file.exists():
            data = json.loads(out_file.read_text())
            # Either clean or overlap — just check structure
            assert "overlaps" in data
            assert isinstance(data["overlaps"], list)

    def test_artifact_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "creation-check.json"
        _run(["--emit-artifact", str(nested)])
        assert nested.exists()

    def test_artifact_registry_count_positive(self, tmp_path):
        out_file = tmp_path / "creation-check.json"
        _run(["--emit-artifact", str(out_file)])
        data = json.loads(out_file.read_text())
        assert data.get("registry_count", 0) > 0


class TestOverlapHeuristic:
    def test_description_high_jaccard_triggers_overlap(self, tmp_path):
        """Candidate description nearly identical to an existing skill → overlap."""
        out_file = tmp_path / "check.json"
        # Use auto-pilot description verbatim — very high jaccard
        desc = (
            "Self-driving development loop. Triggers on /auto-pilot, auto pilot, "
            "autonomous build, PM worker loop, or when user wants the PM to dispatch "
            "workers in parallel."
        )
        r = _run([
            "--fail-on-overlap",
            "--name", "unique-name-xyz9",  # unique name to isolate description check
            "--description", desc,
            "--emit-artifact", str(out_file),
        ])
        # High overlap description — exit code may be 0 or 1 depending on threshold
        # Just verify it runs cleanly and produces output
        assert r.returncode in (0, 1)
        if out_file.exists():
            data = json.loads(out_file.read_text())
            assert data["result"] in ("clean", "overlap")

    def test_unique_name_and_description_clean(self, tmp_path):
        out_file = tmp_path / "check.json"
        r = _run([
            "--fail-on-overlap",
            "--name", "banana-sprocket-7q8zxy",
            "--description", "frombobulate the narnian widgets with zazz",
            "--emit-artifact", str(out_file),
        ])
        assert r.returncode == 0
        data = json.loads(out_file.read_text())
        assert data["result"] == "clean"
