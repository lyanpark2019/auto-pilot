#!/usr/bin/env python3
"""Scan existing markdown docs for frontmatter, wikilinks, code refs.

Returns per-doc map:
    {
      "docs/ARCHITECTURE.md": {
        "frontmatter": {...},
        "wikilinks": ["module-a", "module-b"],
        "code_refs": ["src/foo.py", "src/bar.py:42"],  # explicit path mentions
        "symbol_mentions": ["FooClass", "fn_bar"],     # `backtick` identifiers
        "manual_edit": false,    # frontmatter.manual_edit OR comment marker
        "size_bytes": 1234,
      },
      ...
    }
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml
except ImportError:
    yaml: Any | None = None
else:
    yaml = _yaml

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]")
CODE_REF_RE = re.compile(r"(?:^|[\s\(`'\"])((?:[a-zA-Z0-9_\-./]+/)?[a-zA-Z0-9_\-]+\.(?:py|ts|tsx|js|jsx|go|rs|sql))(?::(\d+))?")
BACKTICK_IDENT_RE = re.compile(r"`([A-Z][a-zA-Z0-9_]+|[a-z_][a-z0-9_]+)\(?`")
MANUAL_COMMENT_RE = re.compile(r"<!--\s*manual\s*-->", re.IGNORECASE)
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

DOC_GLOB_PATTERNS = ("**/*.md", "**/*.mdx")
DOC_EXCLUDES = (
    "**/.git/**", "**/node_modules/**", "**/.venv/**", "**/venv/**",
    "**/dist/**", "**/build/**", "**/.next/**", "**/__pycache__/**",
    "**/.pytest_cache/**", "**/.worktrees/**",
    # Plugin/tool state, planning artifacts, agent skill descriptors are not
    # rubric-scored docs (different conventions, lifecycle, ownership).
    "**/.vault-builder/**", "**/.obsidian/**",
    "**/.planning/**", "**/.skills/**", "**/.claude/**",
)


def _excluded(p: Path, root: Path) -> bool:
    import fnmatch
    rel = str(p.relative_to(root))
    for pat in DOC_EXCLUDES:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, pat.lstrip("**/")):
            return True
    return False


def _parse_frontmatter(text: str) -> dict[str, Any]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    raw = m.group(1)
    if yaml:
        try:
            data = yaml.safe_load(raw) or {}
            return data if isinstance(data, dict) else {}
        except yaml.YAMLError as exc:
            print(f"scan_docs: failed to parse frontmatter YAML: {type(exc).__name__}: {exc}", file=sys.stderr)
            return {}
    # fallback: naive line parser
    fm: dict[str, Any] = {}
    for line in raw.split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("\"'")
    return fm


def scan_doc(path: Path) -> dict[str, Any]:
    text = path.read_text(errors="replace")
    fm = _parse_frontmatter(text)
    body = FRONTMATTER_RE.sub("", text, count=1)

    wikilinks = list({m.group(1).strip() for m in WIKILINK_RE.finditer(body)})
    code_refs = []
    for m in CODE_REF_RE.finditer(body):
        ref = m.group(1)
        line = m.group(2)
        code_refs.append(f"{ref}:{line}" if line else ref)
    code_refs = list(dict.fromkeys(code_refs))   # dedupe preserving order

    symbol_mentions = list({m.group(1) for m in BACKTICK_IDENT_RE.finditer(body)})

    manual = bool(fm.get("manual_edit")) or bool(MANUAL_COMMENT_RE.search(body))

    return {
        "frontmatter": fm,
        "wikilinks": wikilinks,
        "code_refs": code_refs,
        "symbol_mentions": symbol_mentions,
        "manual_edit": manual,
        "size_bytes": path.stat().st_size,
    }


def scan_tree(root: Path) -> dict[str, dict[str, Any]]:
    root = root.expanduser().resolve()
    out: dict[str, dict[str, Any]] = {}
    seen: set[Path] = set()
    for pattern in DOC_GLOB_PATTERNS:
        for p in root.glob(pattern):
            if p in seen or not p.is_file():
                continue
            if _excluded(p, root):
                continue
            seen.add(p)
            rel = str(p.relative_to(root))
            out[rel] = scan_doc(p)
    return out


def main(argv: list[str]) -> int:
    import json
    import sys
    if len(argv) < 2:
        print("usage: scan_docs.py <repo>", file=sys.stderr)
        return 1
    result = scan_tree(Path(argv[1]))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv))
