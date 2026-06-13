#!/usr/bin/env python3
"""Deterministic codex-fork provenance guard.

Verifies that:
  (a) Every directory under codex/skills/*/ has a SKILL.md AND
      (a LICENSE.txt OR LICENSE-upstream.txt), unless the skill name
      is in the self-authored allowlist.
  (b) Every codex/skills/* directory name appears as a row in
      codex/UPSTREAM.md (first-column cell of the Markdown table).
  (c) No UPSTREAM.md data row has a pinned-revision cell equal to the
      literal placeholder "yyyy" or empty string.

Exits non-zero with one message per violation.

Usage:
    python3 scripts/docs/check_codex_provenance.py [--root REPO_ROOT]
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Skills whose absence of a license file is expected (self-authored).
_SELF_AUTHORED: frozenset[str] = frozenset({"codex-orchestra"})

# Column index (0-based) of the pinned-revision cell in the UPSTREAM.md table.
# Table: skill | upstream source URL | upstream license | pinned upstream revision | …
_PIN_COL = 3


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpstreamRow:
    """One parsed data row from the UPSTREAM.md table."""

    skill: str
    pinned_revision: str


def _parse_upstream_table(upstream_md: Path) -> list[UpstreamRow]:
    """Parse the Markdown table in UPSTREAM.md; return one UpstreamRow per data row."""
    rows: list[UpstreamRow] = []
    text = upstream_md.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Split on '|', strip whitespace from each cell.
        raw_cells = [c.strip() for c in line.split("|")]
        # Remove only the leading and trailing empty strings produced by outer pipes.
        if raw_cells and raw_cells[0] == "":
            raw_cells = raw_cells[1:]
        if raw_cells and raw_cells[-1] == "":
            raw_cells = raw_cells[:-1]
        if len(raw_cells) < _PIN_COL + 1:
            continue
        skill_cell = raw_cells[0]
        pin_cell = raw_cells[_PIN_COL]
        # Skip the header row and separator row (--- / ===).
        if re.fullmatch(r"[-=: |]+", line.replace("|", "").strip()):
            continue
        if skill_cell.lower() in {"skill", "---", "==="}:
            continue
        if re.fullmatch(r"[-:]+", skill_cell):
            continue
        rows.append(UpstreamRow(skill=skill_cell, pinned_revision=pin_cell))
    return rows


# ---------------------------------------------------------------------------
# Violation record
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    """One detected provenance violation."""

    message: str


# ---------------------------------------------------------------------------
# Core checks
# ---------------------------------------------------------------------------


def _check_license_files(
    skills_dir: Path,
    upstream_skills: set[str],
) -> list[Violation]:
    """Check (a): every non-allowlisted skill has SKILL.md + a license file."""
    violations: list[Violation] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        name = skill_dir.name
        has_skill_md = (skill_dir / "SKILL.md").is_file()
        if not has_skill_md:
            violations.append(Violation(
                f"codex/skills/{name}: missing SKILL.md"
            ))
        if name in _SELF_AUTHORED:
            continue
        has_license = (
            (skill_dir / "LICENSE.txt").is_file()
            or (skill_dir / "LICENSE-upstream.txt").is_file()
        )
        if not has_license:
            violations.append(Violation(
                f"codex/skills/{name}: missing LICENSE.txt or LICENSE-upstream.txt"
                " (add the file or add the skill to the self-authored allowlist)"
            ))
    return violations


def _check_upstream_rows(
    skills_dir: Path,
    rows: list[UpstreamRow],
) -> list[Violation]:
    """Check (b): every skills/* dir name appears in UPSTREAM.md."""
    violations: list[Violation] = []
    tabled_skills: set[str] = {r.skill for r in rows}
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        name = skill_dir.name
        if name not in tabled_skills:
            violations.append(Violation(
                f"codex/skills/{name}: no matching row in codex/UPSTREAM.md"
                " (add a row with the upstream source and pinned revision)"
            ))
    return violations


def _check_placeholder_revisions(rows: list[UpstreamRow]) -> list[Violation]:
    """Check (c): no pinned-revision cell is the literal 'yyyy' or empty."""
    violations: list[Violation] = []
    for row in rows:
        pin = row.pinned_revision
        if pin == "" or pin.lower() == "yyyy":
            violations.append(Violation(
                f"codex/UPSTREAM.md row '{row.skill}': pinned-revision is"
                f" {'empty' if pin == '' else repr(pin)}"
                " (set a real SHA, 'n/a self-authored', or 'unresolved — TODO')"
            ))
    return violations


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_codex_provenance(repo_root: Path) -> list[Violation]:
    """Run all provenance checks; return a list of violations."""
    violations: list[Violation] = []

    upstream_md = repo_root / "codex" / "UPSTREAM.md"
    skills_dir = repo_root / "codex" / "skills"

    if not upstream_md.is_file():
        violations.append(Violation(
            "codex/UPSTREAM.md is missing — create the provenance ledger"
        ))
        # Cannot check rows without the file; still check license files if skills/ exists.
        if skills_dir.is_dir():
            violations.extend(_check_license_files(skills_dir, set()))
        return violations

    if not skills_dir.is_dir():
        # No skills to check; UPSTREAM.md can still be parsed for placeholder check.
        rows = _parse_upstream_table(upstream_md)
        violations.extend(_check_placeholder_revisions(rows))
        return violations

    rows = _parse_upstream_table(upstream_md)
    tabled_skills: set[str] = {r.skill for r in rows}

    violations.extend(_check_license_files(skills_dir, tabled_skills))
    violations.extend(_check_upstream_rows(skills_dir, rows))
    violations.extend(_check_placeholder_revisions(rows))
    return violations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point: print violations and return exit code."""
    parser = argparse.ArgumentParser(
        description=(
            "Verify codex/skills/ fork provenance:"
            " license files, UPSTREAM.md rows, and pinned revisions."
        )
    )
    parser.add_argument(
        "--root",
        default=".",
        metavar="REPO_ROOT",
        help="Repo root (default: cwd)",
    )
    args = parser.parse_args(argv)
    repo_root = Path(args.root).resolve()

    violations = check_codex_provenance(repo_root)
    if violations:
        sys.stdout.write(
            f"codex-provenance: {len(violations)} violation(s) found\n\n"
        )
        for v in violations:
            sys.stdout.write(f"  {v.message}\n")
        return 1

    sys.stdout.write("codex-provenance: OK (0 violations)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
