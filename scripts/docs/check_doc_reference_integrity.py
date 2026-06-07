#!/usr/bin/env python3
"""
Deterministic doc-reference integrity checker.

Scans docs/*.md, CLAUDE.md, and .claude/**/*.md for file:line citations
(e.g. ``scripts/_dispatch.py:42`` or plain ``vault/pipeline/fix.py:33``).
For each citation:
  (a) the cited file must exist in the repo root;
  (b) the cited line number must be ≤ the file's line count.
  (c) best-effort: if a symbol name appears nearby, warn if it is absent
      from that line's surrounding context (10-line window).

Lines containing ``<!-- cite-ignore -->`` are silently skipped.

Exit: non-zero with a list of violations when any are found.

Usage:
    python3 scripts/docs/check_doc_reference_integrity.py [--root REPO_ROOT]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

# Pattern: optional backtick wrapper, path with extension, colon, line number.
# Captures: (cited_path, line_number).
# Matches both `path/file.py:42` and plain path/file.py:42.
_CITE_RE = re.compile(
    r"`?([a-zA-Z0-9_./~-]+\.[a-zA-Z][a-zA-Z0-9]*):([0-9]+)(?:-([0-9]+))?`?"
)

# Extensions treated as code/text files worth checking.
_CHECKABLE_EXTS = frozenset(
    {".py", ".sh", ".md", ".json", ".yaml", ".yml", ".txt", ".toml"}
)

# Symbol patterns: backtick-wrapped identifiers adjacent to the citation
# (within the same line or prev/next line).
_SYMBOL_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")

# Paths to skip (version-control or build artefacts).
_SKIP_PATH_PREFIXES = ("node_modules/", ".git/", "__pycache__/", ".planning/")

IGNORE_MARKER = "<!-- cite-ignore -->"


class Violation(NamedTuple):
    doc_file: str      # relative path to the doc containing the citation
    doc_line: int      # line number in the doc
    citation: str      # the raw citation text
    reason: str        # human-readable explanation
    suggestion: str    # optional hint (empty string if none)


def _load_file_lines(path: Path) -> list[str] | None:
    """Return 1-indexed lines for a file, or None if unreadable."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def _nearby_symbols(doc_lines: list[str], doc_lineno: int) -> frozenset[str]:
    """Extract backtick-wrapped symbols from lines around ``doc_lineno``."""
    start = max(0, doc_lineno - 3)
    end = min(len(doc_lines), doc_lineno + 2)
    symbols: set[str] = set()
    for ln in doc_lines[start:end]:
        symbols.update(m.group(1) for m in _SYMBOL_RE.finditer(ln))
    return frozenset(symbols)


def _find_symbol_in_window(
    code_lines: list[str], target_line: int, symbols: frozenset[str]
) -> list[str]:
    """Return symbols from ``symbols`` not found in a 10-line window around ``target_line``."""
    window_start = max(0, target_line - 6)
    window_end = min(len(code_lines), target_line + 5)
    window_text = "\n".join(code_lines[window_start:window_end])
    return [s for s in sorted(symbols) if s not in window_text]


def _is_checkable(raw_path: str) -> bool:
    """True if this citation path has an extension we validate."""
    suffix = Path(raw_path).suffix.lower()
    return suffix in _CHECKABLE_EXTS


def _is_skipped_path(raw_path: str) -> bool:
    return any(raw_path.startswith(pfx) for pfx in _SKIP_PATH_PREFIXES)


def _doc_files(repo_root: Path) -> list[Path]:
    """Collect doc files to scan."""
    targets: list[Path] = []

    docs_dir = repo_root / "docs"
    if docs_dir.is_dir():
        targets.extend(docs_dir.rglob("*.md"))

    claude_md = repo_root / "CLAUDE.md"
    if claude_md.exists():
        targets.append(claude_md)

    dot_claude = repo_root / ".claude"
    if dot_claude.is_dir():
        # Exclude ephemeral worktree snapshots — they are not canonical docs.
        worktrees_dir = dot_claude / "worktrees"
        for p in dot_claude.rglob("*.md"):
            if not p.is_relative_to(worktrees_dir):
                targets.append(p)

    return targets


def check_citations(repo_root: Path) -> list[Violation]:
    """Run all citation checks; return a list of violations."""
    violations: list[Violation] = []
    # Cache resolved file line counts to avoid repeated reads.
    _line_count_cache: dict[Path, int | None] = {}
    _lines_cache: dict[Path, list[str] | None] = {}

    def get_lines(p: Path) -> list[str] | None:
        if p not in _lines_cache:
            _lines_cache[p] = _load_file_lines(p)
        return _lines_cache[p]

    def get_line_count(p: Path) -> int | None:
        if p not in _line_count_cache:
            lines = get_lines(p)
            _line_count_cache[p] = len(lines) if lines is not None else None
        return _line_count_cache[p]

    for doc_path in _doc_files(repo_root):
        doc_lines = get_lines(doc_path)
        if doc_lines is None:
            continue
        doc_rel = str(doc_path.relative_to(repo_root))

        for lineno_0, raw_line in enumerate(doc_lines):
            if IGNORE_MARKER in raw_line:
                continue

            for m in _CITE_RE.finditer(raw_line):
                raw_path = m.group(1)
                line_str = m.group(2)
                end_line_str = m.group(3)  # optional range end (e.g. :35-36)
                citation = m.group(0).strip("`")

                if _is_skipped_path(raw_path):
                    continue
                if not _is_checkable(raw_path):
                    continue

                # Strip leading ~/ — those are absolute personal paths, flag as
                # unresolvable but don't crash.
                if raw_path.startswith("~/") or raw_path.startswith("/"):
                    violations.append(Violation(
                        doc_file=doc_rel,
                        doc_line=lineno_0 + 1,
                        citation=citation,
                        reason="absolute/home path citation — cannot resolve from repo root",
                        suggestion="use a repo-relative path",
                    ))
                    continue

                target_path = repo_root / raw_path
                if not target_path.exists():
                    violations.append(Violation(
                        doc_file=doc_rel,
                        doc_line=lineno_0 + 1,
                        citation=citation,
                        reason=f"file not found: {raw_path}",
                        suggestion="verify the path or mark historical with <!-- cite-ignore -->",
                    ))
                    continue

                cited_lineno = int(line_str)
                line_count = get_line_count(target_path)
                if line_count is None:
                    violations.append(Violation(
                        doc_file=doc_rel,
                        doc_line=lineno_0 + 1,
                        citation=citation,
                        reason=f"could not read {raw_path}",
                        suggestion="",
                    ))
                    continue

                if cited_lineno > line_count:
                    violations.append(Violation(
                        doc_file=doc_rel,
                        doc_line=lineno_0 + 1,
                        citation=citation,
                        reason=(
                            f"line {cited_lineno} > file length {line_count} "
                            f"in {raw_path}"
                        ),
                        suggestion=f"{raw_path} has {line_count} lines",
                    ))
                    continue

                # Validate range end if present.
                if end_line_str is not None:
                    end_lineno = int(end_line_str)
                    if end_lineno > line_count:
                        violations.append(Violation(
                            doc_file=doc_rel,
                            doc_line=lineno_0 + 1,
                            citation=citation,
                            reason=(
                                f"range end {end_lineno} > file length {line_count} "
                                f"in {raw_path}"
                            ),
                            suggestion=f"{raw_path} has {line_count} lines",
                        ))
                        continue

                # Best-effort symbol check.
                nearby = _nearby_symbols(doc_lines, lineno_0)
                if nearby:
                    code_lines = get_lines(target_path)
                    if code_lines is not None:
                        missing = _find_symbol_in_window(
                            code_lines, cited_lineno - 1, nearby
                        )
                        if missing:
                            # WARN only — does not fail.
                            print(
                                f"WARN {doc_rel}:{lineno_0 + 1}: symbol(s) "
                                f"{missing} not found near {raw_path}:{cited_lineno}",
                                file=sys.stderr,
                            )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check file:line citations in docs are still valid."
    )
    parser.add_argument(
        "--root",
        default=".",
        metavar="REPO_ROOT",
        help="Repo root (default: cwd)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()
    violations = check_citations(repo_root)

    if violations:
        print(f"doc-reference-integrity: {len(violations)} violation(s) found\n")
        for v in violations:
            print(f"  {v.doc_file}:{v.doc_line}  [{v.citation}]")
            print(f"    reason: {v.reason}")
            if v.suggestion:
                print(f"    suggestion: {v.suggestion}")
        return 1

    print("doc-reference-integrity: OK (0 violations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
