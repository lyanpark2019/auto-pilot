"""generate_env_constraints.sh — idempotent upsert contract (review r1).

The bare `>> CLAUDE.md` instruction duplicated the `## Environment Constraints`
header on every re-run. The script now wraps output in BEGIN/END markers and
`--into FILE` replaces the existing block instead of appending a second one.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skills" / "setup-harness" / "scripts" / "generate_env_constraints.sh"

HEADER = "## Environment Constraints"
BEGIN = "<!-- ENV-CONSTRAINTS:BEGIN"
END = "<!-- ENV-CONSTRAINTS:END -->"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(cwd), timeout=30,
    )


class TestEnvConstraintsIdempotency:
    def test_stdout_mode_is_marker_wrapped(self, tmp_path: Path) -> None:
        r = _run([str(tmp_path)], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        assert r.stdout.count(HEADER) == 1
        assert BEGIN in r.stdout
        assert r.stdout.rstrip().endswith(END)

    def test_into_two_runs_single_block(self, tmp_path: Path) -> None:
        """Two --into runs must leave exactly ONE block (upsert, not append)."""
        target = tmp_path / "CLAUDE.md"
        target.write_text("# Project\n\nexisting content\n")

        r1 = _run([str(tmp_path), "--into", str(target)], cwd=tmp_path)
        assert r1.returncode == 0, r1.stderr
        after_first = target.read_text()
        assert after_first.count(HEADER) == 1
        assert after_first.count(BEGIN) == 1

        r2 = _run([str(tmp_path), "--into", str(target)], cwd=tmp_path)
        assert r2.returncode == 0, r2.stderr
        after_second = target.read_text()
        assert after_second.count(HEADER) == 1, "re-run duplicated the block"
        assert after_second.count(BEGIN) == 1
        assert after_second.count(END) == 1
        # Pre-existing content survives both runs
        assert "existing content" in after_second

    def test_into_creates_missing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "NEW.md"
        r = _run([str(tmp_path), "--into", str(target)], cwd=tmp_path)
        assert r.returncode == 0, r.stderr
        text = target.read_text()
        assert text.count(HEADER) == 1
        assert text.count(BEGIN) == 1

    def test_begin_without_end_fails_cleanly(self, tmp_path: Path) -> None:
        """Hand-corrupted block (BEGIN, no END) → clean refusal, file untouched,
        no python traceback (r2 finding)."""
        target = tmp_path / "CLAUDE.md"
        corrupted = "# Doc\n\n" + BEGIN + " (generate_env_constraints.sh — managed block, do not edit inside) -->\nstuff\n"
        target.write_text(corrupted)
        r = _run([str(tmp_path), "--into", str(target)], cwd=tmp_path)
        assert r.returncode != 0
        assert "END marker missing" in (r.stderr + r.stdout)
        assert "Traceback" not in r.stderr
        assert target.read_text() == corrupted  # untouched
