"""Single source of truth for code-tree exclusion patterns.

Three paths walk a repo and must agree on which dirs to skip, or buckets,
graphs, and drift reports diverge:

- ``sources/code.py``      — source-adapter discover (per-domain vault build)
- ``pipeline/scan_code.py``— public-API scan (adds tests/migrations/vendor)
- ``pipeline/drift.py``    — orphan-detection filesystem walk

Add a junk / worktree / vendored dir to ``BASE_EXCLUDES`` HERE, not in three
copied lists. Callers that need extra exclusions (e.g. scan_code skipping
tests for API extraction) pass them as ``extras``.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

# Machinery / junk dirs every code-walking path skips.
BASE_EXCLUDES: tuple[str, ...] = (
    "**/.git/**", "**/node_modules/**", "**/__pycache__/**", "**/.venv/**",
    "**/venv/**", "**/build/**", "**/dist/**", "**/.next/**", "**/target/**",
    "**/.pytest_cache/**", "**/.mypy_cache/**", "**/coverage/**", "**/.tox/**",
    # Agent worktrees — near-duplicate copies of real source. Without these,
    # a walk ingests ~2x phantom module pages (one per worktree) that pollute
    # buckets, inflate graph god-node degree, and break dedup.
    "**/.codex-worktrees/**", "**/.claude/worktrees/**", "**/.worktrees/**",
)


def is_excluded(path: Path, root: Path, extras: tuple[str, ...] | list[str] = ()) -> bool:
    """True if ``path`` matches any ``BASE_EXCLUDES`` or caller ``extras`` glob.

    Each pattern is tested both as-is (``**/.git/**``) and with the leading
    ``**/`` stripped (``.git/**``) so top-level dirs match too.
    """
    rel = str(path.relative_to(root)) if path.is_absolute() else str(path)
    for pat in (*BASE_EXCLUDES, *extras):
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pat.lstrip("**/")):
            return True
    return False
