"""Tests for scripts/docs/check_asset_counts.py.

TDD: these tests are written before the implementation to pin the expected
behaviour. They verify both the "red" (drift-caught) and "green" (real tree)
paths.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "docs" / "check_asset_counts.py"


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _populate(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Minimal repo with CLAUDE.md that makes correct count claims."""
    # 2 agents
    for name in ("worker.md", "retro.md"):
        _populate(tmp_path / "agents" / name, f"# {name}\n")
    # 3 hook scripts (non-test)
    for name in ("guard.sh", "preflight.py", "check.sh"):
        _populate(tmp_path / "hooks" / name, "#!/usr/bin/env bash\n")
    # stub test file that must be excluded
    _populate(tmp_path / "hooks" / "test_guard.py", "# test\n")
    # 1 schema
    _populate(tmp_path / "schemas" / "contract.schema.json", '{"type":"object"}\n')
    # 2 skill dirs
    _populate(tmp_path / "skills" / "alpha" / "SKILL.md", "# alpha\n")
    _populate(tmp_path / "skills" / "beta" / "SKILL.md", "# beta\n")
    # CLAUDE.md with correct claims
    _populate(
        tmp_path / "CLAUDE.md",
        "- `agents/` — 2 contracts: worker, retro\n"
        "- `hooks/*.sh|*.py` — (3 scripts)\n"
        "- `schemas/` — (1 files, JSON Schema)\n"
        "- `skills/` — 2 dirs / 2 active: alpha, beta\n",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Green path: correct claims pass
# ---------------------------------------------------------------------------


class TestGreenPath:
    def test_correct_counts_exit_zero(self, repo: Path) -> None:
        r = _run(repo)
        assert r.returncode == 0, f"Expected 0 but got {r.returncode}.\nstdout={r.stdout}\nstderr={r.stderr}"
        assert "OK" in r.stdout or "0 mismatch" in r.stdout

    def test_real_repo_exits_zero(self) -> None:
        """The real tree must pass its own checker — the critical regression guard."""
        r = _run(REPO_ROOT)
        assert r.returncode == 0, (
            f"Real repo has count drift!\nstdout={r.stdout}\nstderr={r.stderr}"
        )


# ---------------------------------------------------------------------------
# Red path: drift is caught
# ---------------------------------------------------------------------------


class TestRedPath:
    def test_wrong_agent_count_is_caught(self, repo: Path) -> None:
        """Claiming 99 agent contracts when only 2 exist → exit non-zero."""
        _populate(
            repo / "CLAUDE.md",
            "- `agents/` — 99 contracts: worker, retro\n"
            "- `hooks/*.sh|*.py` — (3 scripts)\n"
            "- `schemas/` — (1 files, JSON Schema)\n"
            "- `skills/` — 2 dirs / 2 active: alpha, beta\n",
        )
        r = _run(repo)
        assert r.returncode != 0
        assert "99" in r.stdout
        assert "agent" in r.stdout.lower() or "contracts" in r.stdout.lower()

    def test_wrong_hook_count_is_caught(self, repo: Path) -> None:
        """Claiming 99 hook scripts when only 3 exist → exit non-zero."""
        _populate(
            repo / "CLAUDE.md",
            "- `agents/` — 2 contracts: worker, retro\n"
            "- `hooks/*.sh|*.py` — (99 scripts)\n"
            "- `schemas/` — (1 files, JSON Schema)\n"
            "- `skills/` — 2 dirs / 2 active: alpha, beta\n",
        )
        r = _run(repo)
        assert r.returncode != 0
        assert "99" in r.stdout

    def test_wrong_schema_count_is_caught(self, repo: Path) -> None:
        """Claiming 99 schema files when only 1 exists → exit non-zero."""
        _populate(
            repo / "CLAUDE.md",
            "- `agents/` — 2 contracts: worker, retro\n"
            "- `hooks/*.sh|*.py` — (3 scripts)\n"
            "- `schemas/` — (99 files, JSON Schema)\n"
            "- `skills/` — 2 dirs / 2 active: alpha, beta\n",
        )
        r = _run(repo)
        assert r.returncode != 0
        assert "99" in r.stdout

    def test_wrong_skills_dir_count_is_caught(self, repo: Path) -> None:
        """Claiming 99 skill dirs when only 2 exist → exit non-zero."""
        _populate(
            repo / "CLAUDE.md",
            "- `agents/` — 2 contracts: worker, retro\n"
            "- `hooks/*.sh|*.py` — (3 scripts)\n"
            "- `schemas/` — (1 files, JSON Schema)\n"
            "- `skills/` — 99 dirs / 99 active: alpha, beta\n",
        )
        r = _run(repo)
        assert r.returncode != 0
        assert "99" in r.stdout

    def test_multiple_mismatches_all_reported(self, repo: Path) -> None:
        """Multiple wrong claims → all reported, single exit 1."""
        _populate(
            repo / "CLAUDE.md",
            "- `agents/` — 99 contracts: worker\n"
            "- `hooks/*.sh|*.py` — (88 scripts)\n"
            "- `schemas/` — (77 files, JSON Schema)\n"
            "- `skills/` — 66 dirs / 66 active\n",
        )
        r = _run(repo)
        assert r.returncode != 0
        stdout = r.stdout
        assert "99" in stdout
        assert "88" in stdout
        assert "77" in stdout
        assert "66" in stdout

    def test_no_claude_md_exits_zero(self, tmp_path: Path) -> None:
        """Repo without CLAUDE.md has no claims to check — should pass cleanly."""
        r = _run(tmp_path)
        assert r.returncode == 0

    def test_test_hooks_excluded(self, repo: Path) -> None:
        """test_*.py files in hooks/ are not counted as hook scripts."""
        # repo fixture has test_guard.py — still must report 3 (not 4)
        r = _run(repo)
        assert r.returncode == 0

    def test_ignore_marker_suppresses_check(self, repo: Path) -> None:
        """Lines with <!-- count-ignore --> are skipped."""
        _populate(
            repo / "CLAUDE.md",
            "- `agents/` — 99 contracts: worker <!-- count-ignore -->\n"
            "- `hooks/*.sh|*.py` — (3 scripts)\n"
            "- `schemas/` — (1 files, JSON Schema)\n"
            "- `skills/` — 2 dirs / 2 active: alpha, beta\n",
        )
        r = _run(repo)
        assert r.returncode == 0, f"ignore marker must suppress: {r.stdout}"
