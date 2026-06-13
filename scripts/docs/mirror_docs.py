#!/usr/bin/env python3
"""Mirror a repo's top-level docs into a Knowledge-vault wiki ROOT, freshness-stamped.

The global ``~/.claude/scripts/vault-sync.sh`` prefers this script over its generic
rsync fallback. It writes the canonical ROOT layout the vault-first discovery rule
reads (``~/Documents/Knowledge/wiki/projects/<project>/<page>.md``), stamps
``source_commit`` = current HEAD so staleness is detectable, and removes the
redundant ``docs/`` subdir the generic fallback would otherwise leave behind.

The vault is a downstream MIRROR, not an edit surface: repo ``docs/`` is the single
source of truth, so pages are always overwritten (the ``manual_edit:true`` preserve
rule from the vault-build exporter does not apply here). Edit repo docs, not the
vault copy. Vault-only content (``nodes/``, ``graphify/``, ``history/``) is untouched.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

TOP_LEVEL_FILES = ("CLAUDE.md", "AGENTS.md", "ARCHITECTURE.md", "README.md")
_FRONT_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_SOURCE_COMMIT_RE = re.compile(r"^source_commit:.*$", re.MULTILINE)
_LAST_SYNCED_RE = re.compile(r"^last_synced:.*$", re.MULTILINE)


@dataclass
class MirrorReport:
    """Outcome of a mirror run."""

    pages_written: int = 0
    docs_subdir_removed: bool = False
    pages: list[str] = field(default_factory=list)


def resolve_commit(repo: Path) -> str:
    """Return repo HEAD sha, or an empty string when git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def stamp_frontmatter(text: str, commit: str, synced: str) -> str:
    """Set ``source_commit``/``last_synced`` in the page frontmatter, creating it if absent."""
    match = _FRONT_RE.search(text)
    if match is None:
        front = f"---\nsource_commit: {commit}\nlast_synced: {synced}\n---\n\n"
        return front + text
    block = match.group(1)
    if _SOURCE_COMMIT_RE.search(block):
        block = _SOURCE_COMMIT_RE.sub(f"source_commit: {commit}", block)
    else:
        block = f"{block}\nsource_commit: {commit}"
    if _LAST_SYNCED_RE.search(block):
        block = _LAST_SYNCED_RE.sub(f"last_synced: {synced}", block)
    else:
        block = f"{block}\nlast_synced: {synced}"
    return text[: match.start()] + f"---\n{block}\n---\n" + text[match.end():]


def _sources(repo: Path, doc_root: Path) -> list[tuple[Path, str]]:
    pairs: list[tuple[Path, str]] = []
    if doc_root.is_dir():
        for src in sorted(doc_root.glob("*.md")):
            if src.name in TOP_LEVEL_FILES:
                continue
            pairs.append((src, src.name))
    for name in TOP_LEVEL_FILES:
        src = repo / name
        if src.is_file():
            pairs.append((src, name))
    return pairs


def _write_index(wiki: Path, project_name: str, synced: str) -> None:
    pages = sorted(
        p.stem for p in wiki.glob("*.md") if p.name != "index.md"
    )
    lines = [
        "---", "type: index", f"project: {project_name}",
        f"auto-generated: {synced}", "---", "",
        f"# {project_name}", "", f"## Pages ({len(pages)})", "",
    ]
    lines += [f"- [[{stem}]]" for stem in pages]
    (wiki / "index.md").write_text("\n".join(lines) + "\n")


def mirror_docs(
    repo: Path, wiki: Path, commit: str, synced: str, doc_root: Path | None = None
) -> MirrorReport:
    """Mirror repo top-level docs + root files into ``wiki`` root, stamped with ``commit``."""
    repo = repo.expanduser().resolve()
    wiki = wiki.expanduser().resolve()
    doc_root = (doc_root or (repo / "docs")).expanduser().resolve()
    wiki.mkdir(parents=True, exist_ok=True)

    report = MirrorReport()
    for src, name in _sources(repo, doc_root):
        stamped = stamp_frontmatter(src.read_text(errors="replace"), commit, synced)
        (wiki / name).write_text(stamped)
        report.pages_written += 1
        report.pages.append(name)

    stale_docs = wiki / "docs"
    if stale_docs.is_dir():
        shutil.rmtree(stale_docs)
        report.docs_subdir_removed = True

    _write_index(wiki, wiki.name, synced)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wiki", required=True, help="vault project dir (mirror target)")
    parser.add_argument("--repo", default=".", help="repo root (default: cwd)")
    parser.add_argument("--doc-root", default=None, help="docs dir (default: <repo>/docs)")
    parser.add_argument("--commit", default=None, help="override HEAD sha (testing)")
    args = parser.parse_args(argv)

    repo = Path(args.repo)
    commit = args.commit or resolve_commit(repo)
    synced = time.strftime("%Y-%m-%d")
    doc_root = Path(args.doc_root) if args.doc_root else None
    report = mirror_docs(repo, Path(args.wiki), commit, synced, doc_root)
    print(
        f"mirror_docs: {report.pages_written} pages → {args.wiki} "
        f"@ {commit[:8] or 'no-git'}"
        + (" (removed docs/ dup)" if report.docs_subdir_removed else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
