#!/usr/bin/env python3
"""Deterministic asset-count drift detector.

Scans CLAUDE.md for well-anchored hardcoded count claims about four asset
classes — agents/*.md contracts, hooks non-test scripts, schemas/*.json files,
and skills/ directories — and verifies each claim against the live filesystem.

Exits non-zero with a clear per-mismatch message when any claim diverges from
the actual count.  Lines containing ``<!-- count-ignore -->`` are silently
skipped.

Design choices:
  - NARROW scope: only the four claims that appear in CLAUDE.md's Layout
    section and are purely mechanical (glob-countable).  Prose that is not
    a simple glob count (e.g. "11 active" where "active" requires semantic
    judgment) is intentionally skipped or validated structurally when safe.
  - ADDITIVE to check_doc_reference_integrity.py: that script already
    validates hooks.json-wired hook counts; this script validates the broader
    prose claim of total non-test *.sh|*.py scripts in hooks/.
  - ROBUST to layout: uses anchored regex patterns that match the exact prose
    form found in CLAUDE.md rather than generic number-hunting.

Usage:
    python3 scripts/docs/check_asset_counts.py [--root REPO_ROOT]
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

IGNORE_MARKER = "<!-- count-ignore -->"

# ---------------------------------------------------------------------------
# Claim descriptors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """One anchored count claim to verify."""

    label: str          # human label for messages
    pattern: re.Pattern[str]  # regex with named group ``num``
    doc_file: str       # doc path relative to repo root (e.g. "CLAUDE.md")


# Anchored patterns: each matches the specific prose form used in CLAUDE.md.
# Named group ``num`` captures the asserted integer.
# Designed to match BOTH the real CLAUDE.md prose and any simplified fixtures.

# "16 contracts" — agents/*.md count
# Matches: "- `agents/` — 16 contracts:"
_AGENTS_RE = re.compile(r"agents/[^—\n]*—\s*(?P<num>\d+)\s+contracts?\b")

# "25 scripts" — total non-test *.sh + *.py in hooks/
# Matches: "... `hooks/hooks.json` (25 scripts)" OR "`hooks/*.sh|*.py` — (25 scripts)"
_HOOKS_SCRIPTS_RE = re.compile(r"hooks/[^\n]*?\((?P<num>\d+)\s+scripts?\)")

# "7 files" — schemas/*.json count
# Matches: "(7 files, JSON Schema)" on any line containing "schemas/"
_SCHEMAS_RE = re.compile(r"schemas/[^\n]*?\((?P<num>\d+)\s+files?,\s*JSON Schema\b")

# "11 dirs" — skills/ directory count
# Matches: "- `skills/` — 11 dirs / 11 active:"
_SKILLS_DIRS_RE = re.compile(r"skills/[^—\n]*—\s*(?P<num>\d+)\s+dirs?\b")

_CLAIMS: list[Claim] = [
    Claim(label="agents/*.md contracts", pattern=_AGENTS_RE, doc_file="CLAUDE.md"),
    Claim(label="hooks/ non-test scripts", pattern=_HOOKS_SCRIPTS_RE, doc_file="CLAUDE.md"),
    Claim(label="schemas/*.json files", pattern=_SCHEMAS_RE, doc_file="CLAUDE.md"),
    Claim(label="skills/ directories", pattern=_SKILLS_DIRS_RE, doc_file="CLAUDE.md"),
]

# ---------------------------------------------------------------------------
# Actual count helpers
# ---------------------------------------------------------------------------


def _count_agents(repo_root: Path) -> int:
    agents_dir = repo_root / "agents"
    if not agents_dir.is_dir():
        return 0
    return sum(1 for p in agents_dir.glob("*.md"))


def _count_hook_scripts(repo_root: Path) -> int:
    hooks_dir = repo_root / "hooks"
    if not hooks_dir.is_dir():
        return 0
    return sum(
        1 for p in hooks_dir.iterdir()
        if p.suffix in {".sh", ".py"} and not p.name.startswith("test_")
    )


def _count_schemas(repo_root: Path) -> int:
    schemas_dir = repo_root / "schemas"
    if not schemas_dir.is_dir():
        return 0
    return sum(1 for p in schemas_dir.glob("*.json"))


def _count_skills_dirs(repo_root: Path) -> int:
    skills_dir = repo_root / "skills"
    if not skills_dir.is_dir():
        return 0
    return sum(1 for p in skills_dir.iterdir() if p.is_dir())


_ACTUAL_COUNT_FUNS = {
    "agents/*.md contracts": _count_agents,
    "hooks/ non-test scripts": _count_hook_scripts,
    "schemas/*.json files": _count_schemas,
    "skills/ directories": _count_skills_dirs,
}

# ---------------------------------------------------------------------------
# Mismatch record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mismatch:
    doc_file: str
    doc_line: int      # 1-based
    claim_label: str
    said: int
    actual: int
    raw_match: str


# ---------------------------------------------------------------------------
# Core checker
# ---------------------------------------------------------------------------


def check_asset_counts(repo_root: Path) -> list[Mismatch]:
    """Return a list of mismatches; empty list means all claims are accurate."""
    mismatches: list[Mismatch] = []

    for claim in _CLAIMS:
        doc_path = repo_root / claim.doc_file
        if not doc_path.exists():
            continue  # no doc to check — treat as clean

        doc_lines = doc_path.read_text(encoding="utf-8", errors="replace").splitlines()
        actual = _ACTUAL_COUNT_FUNS[claim.label](repo_root)

        for lineno_0, raw_line in enumerate(doc_lines):
            if IGNORE_MARKER in raw_line:
                continue
            m = claim.pattern.search(raw_line)
            if m is None:
                continue
            said = int(m.group("num"))
            if said != actual:
                mismatches.append(Mismatch(
                    doc_file=claim.doc_file,
                    doc_line=lineno_0 + 1,
                    claim_label=claim.label,
                    said=said,
                    actual=actual,
                    raw_match=m.group(0),
                ))

    return mismatches


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point: print mismatches and return exit code."""
    parser = argparse.ArgumentParser(
        description="Verify hardcoded asset-count claims in CLAUDE.md against the live filesystem."
    )
    parser.add_argument("--root", default=".", metavar="REPO_ROOT",
                        help="Repo root (default: cwd)")
    args = parser.parse_args(argv)
    repo_root = Path(args.root).resolve()

    mismatches = check_asset_counts(repo_root)
    if mismatches:
        sys.stdout.write(
            f"asset-count-drift: {len(mismatches)} mismatch(es) found\n\n"
        )
        for mm in mismatches:
            sys.stdout.write(
                f"  {mm.doc_file}:{mm.doc_line}  [{mm.raw_match}]\n"
                f"    claim: {mm.claim_label} — said {mm.said}, actual {mm.actual}\n"
                f"    fix: update the count in {mm.doc_file} to {mm.actual}\n"
            )
        return 1

    sys.stdout.write("asset-count-drift: OK (0 mismatches)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
