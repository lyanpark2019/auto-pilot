#!/usr/bin/env python3
"""L3 SHA-freshness check for generated-mirror docs (doc-management MAINTAIN mode).

Zero-LLM: per doc, parse frontmatter `source_commit` + `manual_edit`, collect cited
source paths from the body (backtick path tokens, same style as the L2 guard), run
`git diff --name-only <source_commit>..HEAD -- <paths>`; non-empty -> STALE (prints
doc + changed files). Missing `source_commit` = frontmatter-contract WARN.
`manual_edit: true` docs are skipped. WARN-only gate: ALWAYS exits 0 (blocking would
hold every code PR hostage to doc updates). Known limits (doc-management-system.md
section 9): renames/moves untracked; fenced-code cites ignored (matches L2 guard).

Usage: check_design_doc_freshness.py [DOC_ROOT ...]     default: .claude/design
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PATH_TOKEN = re.compile(r"`([^`\s]+)`")
# Like the L2 guard's PATH_PREFIX: a real source ref starts with a top-level dir.
PATH_PREFIX = re.compile(
    r"^(?:app|src|lib|libs|scripts|hooks|skills|agents|commands|packages|cmd|internal|services|core|api)/"
)
SOURCE_EXT = re.compile(
    r"\.(py|pyi|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|rb|php|c|h|cc|cpp|hpp|cs|sh|bash|sql|swift|scala|vue|svelte|lua|ex|exs)$"
)
FENCE = re.compile(r"```.*?```", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("\"'")
    return fields


def cited_paths(body: str) -> list[str]:
    paths: set[str] = set()
    for token in PATH_TOKEN.findall(FENCE.sub("", body)):
        ref = token.split(":", 1)[0].rstrip("),.;")  # strip `:NNN` / `:symbol` anchors
        if PATH_PREFIX.match(ref) and SOURCE_EXT.search(ref):
            paths.add(ref)
    return sorted(paths)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv[1:]] or [Path(".claude/design")]
    if git("rev-parse", "--git-dir").returncode != 0:
        print("WARN: not a git repository -- freshness needs git history (exit 0)")
        return 0
    scanned = stale = warned = 0
    for root in roots:
        if not root.is_dir():
            print(f"WARN: doc root not found: {root}")
            warned += 1
            continue
        for doc in sorted(root.rglob("*.md")):
            if "_archive" in doc.parts:
                continue  # archived docs are frozen, never checked
            scanned += 1
            meta = parse_frontmatter(doc.read_text(encoding="utf-8", errors="replace"))
            if meta.get("manual_edit", "").lower() == "true":
                print(f"SKIP {doc}: manual_edit=true (automation must not touch)")
                continue
            commit = meta.get("source_commit", "")
            if not commit:
                print(f"WARN {doc}: missing source_commit in frontmatter")
                warned += 1
                continue
            if git("cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
                print(f"WARN {doc}: source_commit {commit} not found in git history")
                warned += 1
                continue
            paths = cited_paths(doc.read_text(encoding="utf-8", errors="replace"))
            if not paths:
                continue  # nothing citable -> nothing to diff
            diff = git("diff", "--name-only", f"{commit}..HEAD", "--", *paths)
            changed = [ln for ln in diff.stdout.splitlines() if ln.strip()]
            if changed:
                stale += 1
                print(f"STALE {doc} (source_commit {commit[:10]}): {len(changed)} cited source file(s) changed:")
                for path in changed:
                    print(f"  - {path}")
    print(f"freshness: {scanned} doc(s) scanned, {stale} STALE, {warned} WARN -- WARN-only gate, exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
