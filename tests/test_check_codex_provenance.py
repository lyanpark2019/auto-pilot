"""Tests for scripts/docs/check_codex_provenance.py."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "docs" / "check_codex_provenance.py"

# Minimal valid UPSTREAM.md table used across fixtures.
_UPSTREAM_HEADER = (
    "| skill | upstream source URL | upstream license"
    " | pinned upstream revision | date of pin | attribution file in-tree |\n"
    "|---|---|---|---|---|---|\n"
)


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: real repo passes
# ---------------------------------------------------------------------------


def test_passes_on_real_repo() -> None:
    """Running against the actual repo must exit 0."""
    r = _run(REPO_ROOT)
    assert r.returncode == 0, (
        f"Real repo has provenance violations!\nstdout={r.stdout}\nstderr={r.stderr}"
    )
    assert "OK" in r.stdout or "0 violation" in r.stdout


# ---------------------------------------------------------------------------
# Test 2: missing UPSTREAM.md row fails
# ---------------------------------------------------------------------------


def test_missing_upstream_row_fails(tmp_path: Path) -> None:
    """A skill dir with no matching row in UPSTREAM.md → non-zero, names the skill."""
    skill_name = "my-skill"
    _write(tmp_path / "codex" / "skills" / skill_name / "SKILL.md", "# skill\n")
    _write(
        tmp_path / "codex" / "skills" / skill_name / "LICENSE-upstream.txt",
        "MIT\n",
    )
    # UPSTREAM.md exists but has NO row for my-skill.
    _write(
        tmp_path / "codex" / "UPSTREAM.md",
        _UPSTREAM_HEADER
        + "| other-skill | https://example.com | MIT | abc123 | 2026-01-01 | other/LICENSE |\n",
    )
    r = _run(tmp_path)
    assert r.returncode != 0
    assert skill_name in r.stdout


# ---------------------------------------------------------------------------
# Test 3: placeholder revision fails
# ---------------------------------------------------------------------------


def test_placeholder_revision_fails(tmp_path: Path) -> None:
    """A row with 'yyyy' or empty pinned-revision → non-zero."""
    skill_name = "my-skill"
    _write(tmp_path / "codex" / "skills" / skill_name / "SKILL.md", "# skill\n")
    _write(
        tmp_path / "codex" / "skills" / skill_name / "LICENSE-upstream.txt",
        "MIT\n",
    )

    # Case 1: 'yyyy' placeholder.
    _write(
        tmp_path / "codex" / "UPSTREAM.md",
        _UPSTREAM_HEADER
        + f"| {skill_name} | https://example.com | MIT | yyyy | 2026-01-01 | x |\n",
    )
    r1 = _run(tmp_path)
    assert r1.returncode != 0, f"Expected non-zero for 'yyyy'; got: {r1.stdout}"

    # Case 2: empty pinned-revision cell.
    _write(
        tmp_path / "codex" / "UPSTREAM.md",
        _UPSTREAM_HEADER
        + f"| {skill_name} | https://example.com | MIT |  | 2026-01-01 | x |\n",
    )
    r2 = _run(tmp_path)
    assert r2.returncode != 0, f"Expected non-zero for empty cell; got: {r2.stdout}"


# ---------------------------------------------------------------------------
# Test 4: self-authored allowlist — no license file required
# ---------------------------------------------------------------------------


def test_self_authored_allowlist_ok(tmp_path: Path) -> None:
    """codex-orchestra with no license file but a valid UPSTREAM.md row → exit 0."""
    _write(
        tmp_path / "codex" / "skills" / "codex-orchestra" / "SKILL.md",
        "# codex-orchestra\n",
    )
    _write(
        tmp_path / "codex" / "UPSTREAM.md",
        _UPSTREAM_HEADER
        + "| codex-orchestra | (self-authored) | (self-authored)"
        " | n/a self-authored | — | (none — self-authored) |\n",
    )
    r = _run(tmp_path)
    assert r.returncode == 0, (
        f"Expected exit 0 for allowlisted self-authored skill; got: {r.stdout}"
    )


# ---------------------------------------------------------------------------
# Test 5: missing license file on a non-allowlisted skill fails
# ---------------------------------------------------------------------------


def test_missing_license_fails(tmp_path: Path) -> None:
    """A non-allowlisted skill with SKILL.md but no LICENSE*.txt → non-zero, names it."""
    skill_name = "foo"
    _write(tmp_path / "codex" / "skills" / skill_name / "SKILL.md", "# foo\n")
    # No LICENSE.txt or LICENSE-upstream.txt.
    _write(
        tmp_path / "codex" / "UPSTREAM.md",
        _UPSTREAM_HEADER
        + f"| {skill_name} | https://example.com | MIT | abc123 | 2026-01-01 | x |\n",
    )
    r = _run(tmp_path)
    assert r.returncode != 0
    assert skill_name in r.stdout
