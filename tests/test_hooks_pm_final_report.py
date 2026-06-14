"""Tests for hooks/pm_final_report.sh — report rotation (keep 20 newest).

Coverage:
  Ledger-only path (NBM_VAULT_PATH unset/empty):
    - test_rotation_keeps_20_newest: N>KEEP → prune oldest, keep 20
    - test_rotation_noop_when_few_reports: N<=KEEP → no deletion
    - test_reentry_guard_skips_all: stop_hook_active=true → no-op

  Vault-branch path (NBM_VAULT_PATH set, vault active via fresh ticket-state.json):
    - test_vault_rotation_keeps_20_newest: N>KEEP in vault/meta/ → prune oldest, keep 20
    - test_vault_rotation_noop_when_few_reports: N<=KEEP → no deletion
    - test_vault_rotation_does_not_touch_proj_dir: rotation in vault/meta/, not proj dir
"""
from __future__ import annotations

import json
import os
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
    os.utime(ledger, None)
    return report_dir


def _make_vault(base: Path) -> Path:
    """Create a minimal vault layout that makes vault_active=1 in the hook.

    The hook checks: -f $vault/meta/ticket-state.json AND find -mtime -1 > 0.
    We create the file and touch it to ensure mtime is within the last 24h.
    """
    vault = base / "vault"
    meta = vault / "meta"
    meta.mkdir(parents=True)
    ts_file = meta / "ticket-state.json"
    ts_file.write_text(json.dumps({"tickets": []}))
    # Ensure mtime is now so find -mtime -1 matches.
    os.utime(ts_file, None)
    return vault


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


# ── Vault-branch rotation tests ──────────────────────────────────────────────
# These exercise the path where NBM_VAULT_PATH is set and vault/meta/
# ticket-state.json is fresh (vault_active=1).  In this mode the hook writes
# the new report to $vault/meta/ and rotates reports there — NOT in the
# project .planning dir.


def test_vault_rotation_keeps_20_newest(tmp_path):
    """Vault mode: 25 pre-existing + 1 new = 26 total → rotation prunes to 20."""
    proj = tmp_path / "proj"
    proj.mkdir()
    vault = _make_vault(tmp_path)
    vault_meta = vault / "meta"

    _seed_reports(vault_meta, 25)

    r = _run_hook(
        HOOK,
        {"stop_hook_active": False},
        cwd=proj,
        env={
            "CLAUDE_PROJECT_DIR": str(proj),
            "NBM_VAULT_PATH": str(vault),
            "VAULT_BUILDER_VAULT": "",
        },
    )
    assert r.returncode == 0, f"hook failed:\n{r.stderr}"

    remaining = sorted(vault_meta.glob("pm-final-report-*.md"))
    assert len(remaining) == 20, (
        f"expected 20 in vault/meta, got {len(remaining)}: {[p.name for p in remaining]}"
    )
    # Oldest seeded files (000001..000006) must be pruned.
    names = [p.name for p in remaining]
    assert "pm-final-report-20260601-000001.md" not in names
    assert "pm-final-report-20260601-000006.md" not in names
    # The newest seeded file must be kept.
    assert "pm-final-report-20260601-000025.md" in names


def test_vault_rotation_noop_when_few_reports(tmp_path):
    """Vault mode: 15 pre-existing + 1 new = 16 total → no deletion (≤20)."""
    proj = tmp_path / "proj"
    proj.mkdir()
    vault = _make_vault(tmp_path)
    vault_meta = vault / "meta"

    _seed_reports(vault_meta, 15)

    r = _run_hook(
        HOOK,
        {"stop_hook_active": False},
        cwd=proj,
        env={
            "CLAUDE_PROJECT_DIR": str(proj),
            "NBM_VAULT_PATH": str(vault),
            "VAULT_BUILDER_VAULT": "",
        },
    )
    assert r.returncode == 0, f"hook failed:\n{r.stderr}"

    remaining = sorted(vault_meta.glob("pm-final-report-*.md"))
    # 15 seeded + 1 newly written = 16, all kept
    assert len(remaining) == 16, (
        f"expected 16 in vault/meta, got {len(remaining)}: {[p.name for p in remaining]}"
    )


def test_vault_rotation_does_not_touch_proj_dir(tmp_path):
    """Vault mode: rotation must target vault/meta/, leaving proj/.planning/ untouched.

    Pre-seed 25 stale reports in proj/.planning/auto-pilot/ (simulating leftover
    files from an earlier ledger-only session).  The vault branch must not prune
    them — it rotates its own vault/meta/ directory only.
    """
    proj = tmp_path / "proj"
    vault = _make_vault(tmp_path)
    vault_meta = vault / "meta"

    # Create proj report dir with 25 seeded files (should survive intact).
    proj_report_dir = proj / ".planning" / "auto-pilot"
    proj_report_dir.mkdir(parents=True)
    _seed_reports(proj_report_dir, 25)
    proj_before = set(proj_report_dir.glob("pm-final-report-*.md"))

    # Seed 25 in vault/meta/ so rotation will fire there.
    _seed_reports(vault_meta, 25)

    r = _run_hook(
        HOOK,
        {"stop_hook_active": False},
        cwd=proj,
        env={
            "CLAUDE_PROJECT_DIR": str(proj),
            "NBM_VAULT_PATH": str(vault),
            "VAULT_BUILDER_VAULT": "",
        },
    )
    assert r.returncode == 0, f"hook failed:\n{r.stderr}"

    # vault/meta/ was rotated to 20.
    vault_remaining = sorted(vault_meta.glob("pm-final-report-*.md"))
    assert len(vault_remaining) == 20, (
        f"vault/meta: expected 20 after rotation, got {len(vault_remaining)}"
    )

    # proj/.planning/auto-pilot/ must still have all 25 — the vault branch
    # must not have touched it.
    proj_after = set(proj_report_dir.glob("pm-final-report-*.md"))
    assert proj_after == proj_before, (
        "vault-branch rotation must not prune proj/.planning/auto-pilot/ reports"
    )
