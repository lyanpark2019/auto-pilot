#!/usr/bin/env python3
"""Inject missing frontmatter into generated-mirror docs (doc-management MAINTAIN mode).

WARNING: stamping source_commit=HEAD asserts the doc is accurate AS OF HEAD.
Run bootstrap only AFTER an AUDIT pass (or on docs you have just verified)
— otherwise you mark unverified/stale docs as fresh and the L3 freshness
gate will silently skip them until the next code change touches their cited paths.

Idempotent: skips docs that already carry all 4 required keys
(type / topic / source_commit / manual_edit). Dry-run by default;
pass --write to apply.

Type inference from path:
  …/architecture/…  → architecture
  …/modules/…       → module
  …/operations/…    → operations
  …/design/…        → design
  …/rules/…         → rules
  (else)             → doc

Usage:
  bootstrap_frontmatter.py [--write] [DOC_ROOT ...]   default DOC_ROOT: docs
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REQUIRED_FRONTMATTER = ("type", "topic", "source_commit", "manual_edit")

_PATH_TYPE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(^|/)architecture/"), "architecture"),
    (re.compile(r"(^|/)modules?/"), "module"),
    (re.compile(r"(^|/)operations?/"), "operations"),
    (re.compile(r"(^|/)design/"), "design"),
    (re.compile(r"(^|/)rules?/"), "rules"),
    (re.compile(r"(^|/)onboarding/"), "onboarding"),
    (re.compile(r"(^|/)references?/"), "reference"),
]


def _infer_type(doc: Path) -> str:
    rel = doc.as_posix()
    for pattern, label in _PATH_TYPE:
        if pattern.search(rel):
            return label
    return "doc"


def _infer_topic(doc: Path) -> str:
    # Use stem; strip leading digits/dashes from e.g. "01-overview" → "overview"
    slug = doc.stem
    slug = re.sub(r"^[\d\-_]+", "", slug)
    return slug.replace("-", " ").replace("_", " ").strip() or doc.stem


def _head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def parse_frontmatter_raw(text: str) -> tuple[dict[str, str], str, str]:
    """Return (fields, frontmatter_block, body) — frontmatter_block includes delimiters."""
    if not text.startswith("---\n"):
        return {}, "", text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, "", text
    fm_block = text[: end + 4]  # includes closing ---
    body = text[end + 4 :]
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("\"'")
    return fields, fm_block, body


def inject_frontmatter(doc: Path, sha: str, write: bool) -> str | None:
    """Return 'SKIP' | 'WRITE' | 'DRY' depending on what would happen."""
    text = doc.read_text(encoding="utf-8", errors="replace")
    fields, fm_block, body = parse_frontmatter_raw(text)

    missing = [k for k in REQUIRED_FRONTMATTER if not fields.get(k, "").strip()]
    if not missing:
        return "SKIP"

    doc_type = fields.get("type", "").strip() or _infer_type(doc)
    doc_topic = fields.get("topic", "").strip() or _infer_topic(doc)
    doc_commit = fields.get("source_commit", "").strip() or sha
    doc_manual = fields.get("manual_edit", "").strip() or "false"

    # Build new frontmatter preserving existing keys + adding/replacing missing ones
    new_keys: dict[str, str] = {
        "type": doc_type,
        "topic": doc_topic,
        "source_commit": doc_commit,
        "manual_edit": doc_manual,
    }
    # Reconstruct: existing lines (updated) + new missing ones
    if fm_block:
        lines = fm_block[4:].split("\n---")[0].splitlines()
        existing_keys_set = set(fields.keys())
        new_fm_lines: list[str] = []
        for line in lines:
            if ":" in line and not line.startswith((" ", "\t", "#")):
                key = line.partition(":")[0].strip()
                if key in new_keys:
                    new_fm_lines.append(f"{key}: {new_keys[key]}")
                else:
                    new_fm_lines.append(line)
            else:
                new_fm_lines.append(line)
        # Append truly missing keys
        for k in REQUIRED_FRONTMATTER:
            if k not in existing_keys_set:
                new_fm_lines.append(f"{k}: {new_keys[k]}")
        new_fm = "---\n" + "\n".join(new_fm_lines) + "\n---"
        new_text = new_fm + body
    else:
        # No frontmatter at all — prepend a fresh block
        fm_lines = [f"{k}: {new_keys[k]}" for k in REQUIRED_FRONTMATTER]
        new_text = "---\n" + "\n".join(fm_lines) + "\n---\n" + text

    if write:
        doc.write_text(new_text, encoding="utf-8")
        return "WRITE"
    return "DRY"


def main(argv: list[str]) -> int:
    write = "--write" in argv
    args = [a for a in argv[1:] if not a.startswith("-")]
    roots = [Path(a) for a in args] or [Path("docs")]

    sha = _head_sha()
    if not sha:
        print("WARN: could not resolve HEAD sha — source_commit will be empty")

    total = skipped = written = dry = 0
    for root in roots:
        if not root.is_dir():
            print(f"WARN: doc root not found: {root}")
            continue
        for doc in sorted(root.rglob("*.md")):
            if "_archive" in doc.parts:
                continue
            total += 1
            result = inject_frontmatter(doc, sha, write)
            if result == "SKIP":
                skipped += 1
            elif result == "WRITE":
                written += 1
                print(f"WRITE {doc}")
            else:
                dry += 1
                print(f"DRY   {doc}  (pass --write to apply)")

    mode = "WRITE" if write else "DRY-RUN"
    print(
        f"bootstrap_frontmatter [{mode}]: {total} scanned, "
        f"{skipped} already complete, {written if write else dry} need(ed) injection"
        + ("" if write else " — re-run with --write to apply")
    )
    return 0


def demo() -> None:
    """Self-check: create a temp md, bootstrap, assert all 4 keys present."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        docs = Path(tmp) / "docs"
        docs.mkdir()
        md = docs / "some-module.md"
        md.write_text("# Hello\n\nSome content.\n", encoding="utf-8")

        # Dry-run first — file must not change
        original = md.read_text()
        inject_frontmatter(md, sha="abc123def456" * 3, write=False)
        assert md.read_text() == original, "dry-run must not modify file"

        # Write run
        result = inject_frontmatter(md, sha="abc123def456abc123def456abc123def456abc1", write=True)
        assert result == "WRITE", f"expected WRITE, got {result!r}"

        text = md.read_text()
        fields, _, _ = parse_frontmatter_raw(text)
        for key in REQUIRED_FRONTMATTER:
            assert fields.get(key, "").strip(), f"key {key!r} missing after bootstrap"

        sha_val = fields["source_commit"]
        assert len(sha_val) >= 7 and all(c in "0123456789abcdef" for c in sha_val), (
            f"source_commit looks wrong: {sha_val!r}"
        )

        # Idempotency: second inject → SKIP
        result2 = inject_frontmatter(md, sha="abc123def456abc123def456abc123def456abc1", write=True)
        assert result2 == "SKIP", f"expected SKIP on second run, got {result2!r}"

    print("bootstrap_frontmatter demo: all assertions passed")


if __name__ == "__main__":
    if "--demo" in sys.argv or (
        len(sys.argv) == 1 and sys.argv[0].endswith("bootstrap_frontmatter.py")
    ):
        demo()
        sys.exit(0)
    sys.exit(main(sys.argv))
