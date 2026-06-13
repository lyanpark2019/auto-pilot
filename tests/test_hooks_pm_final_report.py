"""Tests for hooks/pm_final_report.sh — report rotation (keep 20 newest)."""
from __future__ import annotations

import json
from pathlib import Path

from _hook_helpers import _run_hook

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "hooks" / "pm_final_report.sh"


def _make_report_dir(base: Path) -> Path:
    """Create a project layout that satisfies pm_final_report.sh conditions."""
    proj = base / "proj"
    report_dir = proj / ".planning" / "auto-pilot"
    report_dir.mkdir(parents=True)
    ledger = report_dir / "session-artifacts.jsonl"
    ledger.write_text(
        json.dumps({"path": "docs/specs/x.md", "op": "write"}) + "\n"
    )
    # Touch ledger so find -mtime -1 matches it.
    import os
    os.utime(ledger, None)
    return report_dir


def _seed_reports(report_dir: Path, count: int) -> None:
    for i in range(1, count + 1):
        fname = f"pm-final-report-20260601-{i:06d}.md"
        (report_dir / fname).write_text(f"# Report {i}\n")


def test_rotation_keeps_20_newest(tmp_path):
    # Seed 25 old reports; hook writes 1 new report (total 26), then rotates to 20.
    report_dir = _make_report_dir(tmp_path)
    _seed_reports(report_dir, 25)

    proj = tmp_path / "proj"
    r = _run_hook(
        HOOK,
        {"stop_hook_active": False},
        cwd=proj,
        env={"CLAUDE_PROJECT_DIR": str(proj), "NBM_VAULT_PATH": "", "VAULT_BUILDER_VAULT": ""},
    )
    assert r.returncode == 0, f"hook failed:\n{r.stderr}"

    remaining = sorted(report_dir.glob("pm-final-report-*.md"))
    assert len(remaining) == 20, f"expected 20, got {len(remaining)}: {[p.name for p in remaining]}"
    # Oldest seeded files should have been pruned; the new report (current datetime) is kept.
    # All 20 remaining should be the 19 newest seeded + the newly written report.
    names = [p.name for p in remaining]
    assert "pm-final-report-20260601-000001.md" not in names


def test_rotation_noop_when_few_reports(tmp_path):
    # Seed 15 reports; hook writes 1 new = 16 total, all kept (≤20).
    report_dir = _make_report_dir(tmp_path)
    _seed_reports(report_dir, 15)

    proj = tmp_path / "proj"
    r = _run_hook(
        HOOK,
        {"stop_hook_active": False},
        cwd=proj,
        env={"CLAUDE_PROJECT_DIR": str(proj), "NBM_VAULT_PATH": "", "VAULT_BUILDER_VAULT": ""},
    )
    assert r.returncode == 0
    remaining = sorted(report_dir.glob("pm-final-report-*.md"))
    # 15 seeded + 1 newly written = 16 total, all kept
    assert len(remaining) == 16


def test_reentry_guard_skips_all(tmp_path):
    """stop_hook_active=true must exit 0 without producing any report."""
    report_dir = _make_report_dir(tmp_path)
    _seed_reports(report_dir, 25)
    before = set(report_dir.glob("pm-final-report-*.md"))

    proj = tmp_path / "proj"
    r = _run_hook(
        HOOK,
        {"stop_hook_active": True},
        cwd=proj,
        env={"CLAUDE_PROJECT_DIR": str(proj), "NBM_VAULT_PATH": "", "VAULT_BUILDER_VAULT": ""},
    )
    assert r.returncode == 0
    after = set(report_dir.glob("pm-final-report-*.md"))
    # No new reports written, no files deleted — reentry guard fired immediately
    assert after == before
