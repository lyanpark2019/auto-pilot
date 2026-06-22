#!/usr/bin/env python3
"""Expand a changed-source-file list into an impact set of docs that cite them.

Workflow:
  1. For each changed source file, derive symbol(s) via graphify affected
     (falls back to basename when graphify is absent or fails).
  2. Collect every .md under DOC_ROOT that mentions any affected symbol or path
     (basename match or ::symbol anchor).
  3. Print the deduped sorted doc path set — this is the "refresh impact" list
     for MAINTAIN mode to consume.

Usage:
  affected_docs.py [--doc-root PATH] [--graph PATH] [FILE ...]
  echo 'app/foo.py' | affected_docs.py --doc-root docs

Flags:
  --doc-root PATH   Directory to scan for docs (default: docs)
  --graph PATH      graphify graph.json path (default: graphify-out/graph.json)
  --depth N         graphify affected depth (default: 1)
  FILE ...          Changed source files (positional args OR stdin, one per line)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_ANCHOR = re.compile(r"`([^`\s]+)`|::(\S+)")  # backtick token or ::symbol anchor
_FENCE = re.compile(r"```.*?```", re.DOTALL)


def _run(*args: str) -> tuple[int, str]:
    r = subprocess.run(list(args), capture_output=True, text=True, check=False)
    return r.returncode, r.stdout


def graphify_affected(symbol: str, graph: Path, depth: int) -> list[str]:
    """Run graphify affected and return affected paths/symbols (may be empty)."""
    rc, out = _run(
        "graphify",
        "affected",
        symbol,
        "--graph",
        str(graph),
        "--depth",
        str(depth),
    )
    if rc != 0 or not out.strip():
        return []
    # graphify affected typically prints one path or symbol per line
    results: list[str] = []
    for line in out.splitlines():
        line = line.strip().lstrip("- ").strip()
        if line:
            results.append(line)
    return results


def derive_symbols(changed_file: str, graph: Path, depth: int) -> list[str]:
    """Return a set of symbols/basenames to search for in docs."""
    p = Path(changed_file)
    basenames = {p.name, p.stem}
    symbols: set[str] = set(basenames)

    if graph.exists():
        for sym in [p.as_posix(), p.stem]:
            for affected in graphify_affected(sym, graph, depth):
                symbols.add(affected)
                symbols.add(Path(affected).name)
                symbols.add(Path(affected).stem)

    return sorted(symbols)


def docs_citing(symbols: list[str], doc_root: Path) -> list[Path]:
    """Grep DOC_ROOT for .md files mentioning any symbol."""
    if not doc_root.is_dir():
        return []
    pattern = re.compile("|".join(re.escape(s) for s in symbols if s))
    hits: list[Path] = []
    for doc in sorted(doc_root.rglob("*.md")):
        if "_archive" in doc.parts:
            continue
        text = doc.read_text(encoding="utf-8", errors="replace")
        # search outside fenced blocks
        body = _FENCE.sub("", text)
        if pattern.search(body):
            hits.append(doc)
    return hits


def main(argv: list[str]) -> int:
    # Parse flags
    doc_root = Path("docs")
    graph = Path("graphify-out/graph.json")
    depth = 1
    positional: list[str] = []
    i = 1
    while i < len(argv):
        if argv[i] == "--doc-root" and i + 1 < len(argv):
            doc_root = Path(argv[i + 1])
            i += 2
        elif argv[i] == "--graph" and i + 1 < len(argv):
            graph = Path(argv[i + 1])
            i += 2
        elif argv[i] == "--depth" and i + 1 < len(argv):
            depth = int(argv[i + 1])
            i += 2
        elif not argv[i].startswith("-"):
            positional.append(argv[i])
            i += 1
        else:
            i += 1

    # Changed files: positional args or stdin
    if positional:
        changed = positional
    elif not sys.stdin.isatty():
        changed = [ln.strip() for ln in sys.stdin if ln.strip()]
    else:
        print("WARN: no changed files supplied — nothing to expand", file=sys.stderr)
        return 0

    all_symbols: list[str] = []
    for cf in changed:
        syms = derive_symbols(cf, graph, depth)
        all_symbols.extend(syms)
    all_symbols = sorted(set(all_symbols))

    if not all_symbols:
        print("WARN: no symbols derived from changed files", file=sys.stderr)
        return 0

    hits = docs_citing(all_symbols, doc_root)
    if hits:
        for doc in hits:
            print(doc)
    else:
        print("INFO: no docs cite the affected symbols", file=sys.stderr)

    return 0


def demo() -> None:
    """Self-check: a doc citing a changed file's basename must be selected."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        docs = Path(tmp) / "docs"
        docs.mkdir()

        # Doc that cites the changed file's basename
        citing = docs / "overview.md"
        citing.write_text(
            "---\ntype: doc\n---\n\nSee `app/publisher.py` for detail.\n",
            encoding="utf-8",
        )
        # Doc that does NOT cite it
        unrelated = docs / "unrelated.md"
        unrelated.write_text("---\ntype: doc\n---\n\nNothing relevant here.\n", encoding="utf-8")

        # Derive symbols for app/publisher.py WITHOUT graphify
        syms = derive_symbols("app/publisher.py", Path("/nonexistent/graph.json"), 1)
        assert "publisher.py" in syms, f"basename not in symbols: {syms}"
        assert "publisher" in syms, f"stem not in symbols: {syms}"

        hits = docs_citing(syms, docs)
        assert citing in hits, f"citing doc not found in hits: {hits}"
        assert unrelated not in hits, f"unrelated doc wrongly included: {hits}"

    print("affected_docs demo: all assertions passed")


if __name__ == "__main__":
    if "--demo" in sys.argv or (len(sys.argv) == 1 and sys.argv[0].endswith("affected_docs.py")):
        demo()
        sys.exit(0)
    sys.exit(main(sys.argv))
