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
Also enforces inventory counts: live asset-count claims and free-text
hook-count claims ("(N scripts)" / "N hooks") on the wiring-SoT pages must
match the real inventory (hooks/hooks.json for hook counts).

Lines containing ``<!-- cite-ignore -->`` are silently skipped.
Exit: non-zero with a list of violations when any are found.

Usage:
    python3 scripts/docs/check_doc_reference_integrity.py [--root REPO_ROOT]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Iterable, Mapping
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

_ASSET_COUNT_RE = re.compile(
    r"(?<![<≤>≥=])\b(?P<num>\d+)\s+"
    r"(?P<kind>codex[- ]skills?|skills?|agents?|commands?|hooks?|assets?)\b",
    re.IGNORECASE,
)
_CANONICAL_ASSET_RE = re.compile(r"\b(?:canonical|registry at)\s+(?P<num>\d+)\b", re.IGNORECASE)
_HISTORICAL_RE = re.compile(
    r"\b(historical|snapshot|recorded|before consolidation|legacy|retired|removed|"
    r"deleted|absorbed|prior|round-[0-9]+)\b",
    re.IGNORECASE,
)
_SOURCE_COMMENT_RE = re.compile(r"^\s*(#|//|/\*|\*)")
_SOURCE_COMMENT_ROOTS = ("scripts", "hooks", "swarm", "vault")
_SOURCE_COMMENT_EXTS = frozenset({".py", ".sh", ".mjs", ".js", ".ts"})

# Free-text hook-count claims ("(22 scripts)" / "22 hooks") tied to the
# hooks.json enumeration. Narrow on purpose: only the wiring-SoT pages, only
# lines that name hooks.json, never the asset-count line (own guard).
_HOOK_DECL_RE = re.compile(r"\b(?P<num>\d+)\s+(?P<kind>scripts|hooks)\b", re.IGNORECASE)
_HOOK_REF_RE = re.compile(r"hooks/([\w-]+\.(?:sh|py))")
_HOOK_COUNT_DOCS = ("CLAUDE.md", "docs/architecture.md")

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


_ASSET_TYPE_TO_KIND = {
    "skill": "skills", "agent": "agents", "command": "commands",
    "hook": "hooks", "codex-skill": "codex-skills",
}


def _asset_counts_from_assets(assets: Iterable[Mapping[str, object]]) -> dict[str, int]:
    counts = {"skills": 0, "agents": 0, "commands": 0, "hooks": 0, "codex-skills": 0}
    shells = 0
    for asset in assets:
        typ = str(asset.get("type", ""))
        if typ == "skill-shell":
            shells += 1
        elif typ in _ASSET_TYPE_TO_KIND:
            counts[_ASSET_TYPE_TO_KIND[typ]] += 1
    counts["assets"] = sum(counts.values()) + shells
    return counts


def _collect_assets_via_dashboard(repo_root: Path) -> list[dict[str, object]] | None:
    module_path = repo_root / "scripts" / "build_dashboard_data.py"
    if not module_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("_auto_pilot_build_dashboard_data", module_path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    collect = getattr(module, "collect_assets", None)
    if not callable(collect):
        return None
    loaded = collect()
    return loaded if isinstance(loaded, list) else None


def _collect_asset_counts(repo_root: Path) -> dict[str, int]:
    assets = _collect_assets_via_dashboard(repo_root)
    if assets is not None:
        return _asset_counts_from_assets(assets)
    fallback: list[dict[str, object]] = []
    skills_dir = repo_root / "skills"
    if skills_dir.is_dir():
        fallback.extend({"type": "skill", "name": p.parent.name} for p in skills_dir.glob("*/SKILL.md"))
        fallback.extend({"type": "skill-shell", "name": p.name}
                        for p in skills_dir.iterdir() if p.is_dir() and not (p / "SKILL.md").exists())
    for sub, typ in (("agents", "agent"), ("commands", "command")):
        base = repo_root / sub
        if base.is_dir():
            fallback.extend({"type": typ, "name": p.stem} for p in base.glob("*.md"))
    hooks_dir = repo_root / "hooks"
    if hooks_dir.is_dir():
        fallback.extend({"type": "hook", "name": p.name} for p in hooks_dir.iterdir()
                        if p.suffix in {".py", ".sh"} and not p.name.startswith("test_"))
    codex_dir = repo_root / "codex" / "skills"
    if codex_dir.is_dir():
        fallback.extend({"type": "codex-skill", "name": p.name} for p in codex_dir.iterdir() if p.is_dir())
    return _asset_counts_from_assets(fallback)


def _asset_kind(raw_kind: str) -> str:
    kind = raw_kind.lower().replace(" ", "-").rstrip("s")
    return _ASSET_TYPE_TO_KIND.get(kind, "assets")


def _has_asset_count_context(raw_line: str) -> bool:
    lower = raw_line.lower()
    if _HISTORICAL_RE.search(raw_line):
        return False
    return (
        "live asset counts" in lower
        or "collect_assets" in lower
        or "build_dashboard_data" in lower
        or ("assets total" in lower and "=" in lower)
    )


def _asset_count_claims(raw_line: str) -> list[tuple[str, int, str]]:
    claims = [
        (_asset_kind(m.group("kind")), int(m.group("num")), m.group(0))
        for m in _ASSET_COUNT_RE.finditer(raw_line)
    ]
    if "collect_assets" in raw_line or "build_dashboard_data" in raw_line:
        claims.extend(("assets", int(m.group("num")), m.group(0))
                      for m in _CANONICAL_ASSET_RE.finditer(raw_line))
    return claims


def _actual_hook_count(repo_root: Path) -> int | None:
    """Unique hooks/<name>.(sh|py) scripts wired in hooks/hooks.json."""
    try:
        text = (repo_root / "hooks" / "hooks.json").read_text(encoding="utf-8")
        blob = json.dumps(json.loads(text))
    except (OSError, json.JSONDecodeError):
        return None
    return len(set(_HOOK_REF_RE.findall(blob)))


def _is_hook_count_line(raw_line: str) -> bool:
    """True only for hooks.json-enumeration lines (not the asset-count line)."""
    if _HISTORICAL_RE.search(raw_line):
        return False
    if "collect_assets" in raw_line or "build_dashboard_data" in raw_line:
        return False
    return "hooks.json" in raw_line


def _check_hook_count_line(
    actual: int | None, doc_rel: str, doc_lineno_0: int, raw_line: str,
) -> list[Violation]:
    if actual is None or doc_rel not in _HOOK_COUNT_DOCS:
        return []
    if not _is_hook_count_line(raw_line):
        return []
    return [
        _violation(
            doc_rel, doc_lineno_0, m.group(0),
            f"hook-count mismatch: said {int(m.group('num'))} {m.group('kind')}, "
            f"actual {actual} (unique hooks/*.sh|.py in hooks/hooks.json)",
            "update the count to match hooks/hooks.json",
        )
        for m in _HOOK_DECL_RE.finditer(raw_line)
        if int(m.group("num")) != actual
    ]


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
        targets.extend(p for p in dot_claude.rglob("*.md")
                       if not p.is_relative_to(worktrees_dir))
    return targets


def _source_comment_files(repo_root: Path) -> list[Path]:
    targets: list[Path] = []
    for root_name in _SOURCE_COMMENT_ROOTS:
        root = repo_root / root_name
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in _SOURCE_COMMENT_EXTS:
                continue
            if any(part in {"tests", "__pycache__"} for part in p.parts):
                continue
            targets.append(p)
    return targets


def _check_asset_count_line(
    counts: dict[str, int], doc_rel: str, doc_lineno_0: int, raw_line: str,
) -> list[Violation]:
    if not _has_asset_count_context(raw_line):
        return []
    violations: list[Violation] = []
    for kind, said, citation in _asset_count_claims(raw_line):
        actual = counts[kind]
        if said == actual:
            continue
        violations.append(_violation(
            doc_rel, doc_lineno_0, citation,
            f"asset count mismatch: {kind}: said {said}, actual {actual}",
            "update the claim from current asset inventory or mark it historical",
        ))
    return violations


class _FileCache:
    """Memoised line loader — avoids repeated disk reads across citations."""

    def __init__(self) -> None:
        self._lines: dict[Path, list[str] | None] = {}
        self._counts: dict[Path, int | None] = {}

    def get_lines(self, p: Path) -> list[str] | None:
        if p not in self._lines:
            self._lines[p] = _load_file_lines(p)
        return self._lines[p]

    def get_line_count(self, p: Path) -> int | None:
        if p not in self._counts:
            lines = self.get_lines(p)
            self._counts[p] = len(lines) if lines is not None else None
        return self._counts[p]


def _warn_symbols(
    cache: _FileCache, doc_lines: list[str], doc_rel: str, doc_lineno_0: int,
    target_path: Path, raw_path: str, cited_lineno: int,
) -> None:
    """Emit a WARN to stderr when nearby symbols are absent from the cited line window."""
    nearby = _nearby_symbols(doc_lines, doc_lineno_0)
    if not nearby:
        return
    code_lines = cache.get_lines(target_path)
    if code_lines is None:
        return
    missing = _find_symbol_in_window(code_lines, cited_lineno - 1, nearby)
    if missing:
        sys.stderr.write(
            f"WARN {doc_rel}:{doc_lineno_0 + 1}: symbol(s) "
            f"{missing} not found near {raw_path}:{cited_lineno}\n"
        )


def _check_path_resolvable(
    doc_rel: str, doc_lineno_0: int, citation: str,
    raw_path: str, repo_root: Path,
) -> tuple[Path, None] | tuple[None, Violation]:
    """Validate that raw_path is relative and exists; return (target_path, None) or (None, violation)."""
    if raw_path.startswith("~/") or raw_path.startswith("/"):
        return None, _violation(
            doc_rel, doc_lineno_0, citation,
            "absolute/home path citation — cannot resolve from repo root",
            "use a repo-relative path",
        )
    target_path = repo_root / raw_path
    if not target_path.exists():
        return None, _violation(
            doc_rel, doc_lineno_0, citation,
            f"file not found: {raw_path}",
            "verify the path or mark historical with <!-- cite-ignore -->",
        )
    return target_path, None


def _violation(
    doc_rel: str, doc_lineno_0: int, citation: str,
    reason: str, suggestion: str,
) -> Violation:
    return Violation(
        doc_file=doc_rel, doc_line=doc_lineno_0 + 1,
        citation=citation, reason=reason, suggestion=suggestion,
    )


def _check_line_bounds(
    cache: _FileCache, doc_rel: str, doc_lineno_0: int, citation: str,
    raw_path: str, target_path: Path, line_str: str, end_line_str: str | None,
) -> Violation | None:
    """Return a Violation if cited line or range end is out of bounds, else None."""
    cited_lineno = int(line_str)
    line_count = cache.get_line_count(target_path)
    if line_count is None:
        return _violation(doc_rel, doc_lineno_0, citation, f"could not read {raw_path}", "")
    if cited_lineno > line_count:
        return _violation(
            doc_rel, doc_lineno_0, citation,
            f"line {cited_lineno} > file length {line_count} in {raw_path}",
            f"{raw_path} has {line_count} lines",
        )
    if end_line_str is not None:
        end_lineno = int(end_line_str)
        if end_lineno > line_count:
            return _violation(
                doc_rel, doc_lineno_0, citation,
                f"range end {end_lineno} > file length {line_count} in {raw_path}",
                f"{raw_path} has {line_count} lines",
            )
    return None


def _check_citation(
    cache: _FileCache, repo_root: Path, doc_rel: str, doc_lines: list[str],
    doc_lineno_0: int, raw_path: str, line_str: str, end_line_str: str | None,
    citation: str,
) -> Violation | None:
    """Validate one citation match; return a Violation or None (clean / WARN-only)."""
    target_path, path_violation = _check_path_resolvable(
        doc_rel, doc_lineno_0, citation, raw_path, repo_root
    )
    if path_violation is not None:
        return path_violation
    assert target_path is not None
    bounds_violation = _check_line_bounds(
        cache, doc_rel, doc_lineno_0, citation, raw_path,
        target_path, line_str, end_line_str,
    )
    if bounds_violation is not None:
        return bounds_violation
    _warn_symbols(
        cache, doc_lines, doc_rel, doc_lineno_0,
        target_path, raw_path, int(line_str),
    )
    return None


def _check_doc_lines(
    repo_root: Path, cache: _FileCache, asset_counts: dict[str, int],
    hook_count: int | None, doc_path: Path,
) -> list[Violation]:
    violations: list[Violation] = []
    doc_lines = cache.get_lines(doc_path)
    if doc_lines is None:
        return violations
    doc_rel = str(doc_path.relative_to(repo_root))
    for lineno_0, raw_line in enumerate(doc_lines):
        if IGNORE_MARKER in raw_line:
            continue
        violations.extend(_check_asset_count_line(asset_counts, doc_rel, lineno_0, raw_line))
        violations.extend(_check_hook_count_line(hook_count, doc_rel, lineno_0, raw_line))
        for m in _CITE_RE.finditer(raw_line):
            raw_path = m.group(1)
            if _is_skipped_path(raw_path) or not _is_checkable(raw_path):
                continue
            v = _check_citation(
                cache, repo_root, doc_rel, doc_lines, lineno_0,
                raw_path, m.group(2), m.group(3), m.group(0).strip("`"),
            )
            if v is not None:
                violations.append(v)
    return violations


def _check_source_comment_lines(
    repo_root: Path, cache: _FileCache,
    asset_counts: dict[str, int], source_path: Path,
) -> list[Violation]:
    source_lines = cache.get_lines(source_path)
    if source_lines is None:
        return []
    source_rel = str(source_path.relative_to(repo_root))
    violations: list[Violation] = []
    for lineno_0, raw_line in enumerate(source_lines):
        if IGNORE_MARKER in raw_line or not _SOURCE_COMMENT_RE.search(raw_line):
            continue
        violations.extend(_check_asset_count_line(asset_counts, source_rel, lineno_0, raw_line))
    return violations

def check_citations(repo_root: Path) -> list[Violation]:
    """Run all citation checks; return a list of violations."""
    cache = _FileCache()
    asset_counts = _collect_asset_counts(repo_root)
    hook_count = _actual_hook_count(repo_root)
    violations: list[Violation] = []
    for doc_path in _doc_files(repo_root):
        violations.extend(_check_doc_lines(repo_root, cache, asset_counts, hook_count, doc_path))
    for source_path in _source_comment_files(repo_root):
        violations.extend(_check_source_comment_lines(repo_root, cache, asset_counts, source_path))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check file:line citations in docs are still valid."
    )
    parser.add_argument("--root", default=".", metavar="REPO_ROOT",
                        help="Repo root (default: cwd)")
    args = parser.parse_args(argv)
    repo_root = Path(args.root).resolve()
    violations = check_citations(repo_root)
    if violations:
        sys.stdout.write(f"doc-reference-integrity: {len(violations)} violation(s) found\n\n")
        for v in violations:
            sys.stdout.write(f"  {v.doc_file}:{v.doc_line}  [{v.citation}]\n")
            sys.stdout.write(f"    reason: {v.reason}\n")
            if v.suggestion:
                sys.stdout.write(f"    suggestion: {v.suggestion}\n")
        return 1

    sys.stdout.write("doc-reference-integrity: OK (0 violations)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
