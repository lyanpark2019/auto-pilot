#!/usr/bin/env python3
"""Drift detector: cross-reference code scan ↔ docs scan.

Four drift types:
- gap          : code module with no doc reference (under-documented)
- orphan       : doc references non-existent code path (dead reference)
- symbol_drift : doc mentions symbol that no longer exists in code
- claim_drift  : doc signature mention contradicts current code signature

Output: drift report (dict) + markdown summary.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Support running both as `python3 -m pipeline.drift` and `python3 pipeline/drift.py`
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pipeline import scan_code, scan_docs
else:
    from pipeline import scan_code, scan_docs

from sources._excludes import is_excluded


@dataclass
class DriftReport:
    repo_root: str
    code_modules: int
    doc_files: int
    gap: list[dict] = field(default_factory=list)
    orphan: list[dict] = field(default_factory=list)
    symbol_drift: list[dict] = field(default_factory=list)
    claim_drift: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_root": self.repo_root,
            "code_modules": self.code_modules,
            "doc_files": self.doc_files,
            "summary": {
                "gap": len(self.gap),
                "orphan": len(self.orphan),
                "symbol_drift": len(self.symbol_drift),
                "claim_drift": len(self.claim_drift),
            },
            "gap": self.gap,
            "orphan": self.orphan,
            "symbol_drift": self.symbol_drift,
            "claim_drift": self.claim_drift,
        }

    def to_markdown(self) -> str:
        lines = [f"# Drift Report — {self.repo_root}", ""]
        lines.append(f"- Code modules scanned: **{self.code_modules}**")
        lines.append(f"- Doc files scanned: **{self.doc_files}**")
        lines.append("")
        lines.append("## Summary")
        lines.append("| Type | Count | Action |")
        lines.append("|---|---|---|")
        lines.append(f"| Gap (undocumented) | {len(self.gap)} | vault-knowledge-author worker |")
        lines.append(f"| Orphan (dead ref) | {len(self.orphan)} | vault-structure-curator worker |")
        lines.append(f"| Symbol drift | {len(self.symbol_drift)} | vault-knowledge-author worker |")
        lines.append(f"| Claim drift (signature) | {len(self.claim_drift)} | vault-knowledge-author worker |")
        lines.append("")

        for title, items, fields in [
            ("Gap", self.gap, ("module",)),
            ("Orphan", self.orphan, ("doc", "ref")),
            ("Symbol drift", self.symbol_drift, ("doc", "symbol")),
            ("Claim drift", self.claim_drift, ("doc", "symbol", "doc_says", "code_has")),
        ]:
            if not items:
                continue
            lines.append(f"## {title}")
            lines.append("")
            for item in items[:50]:
                parts = [f"**{item.get(f, '?')}**" if i == 0 else f"`{item.get(f, '?')}`"
                         for i, f in enumerate(fields)]
                lines.append(f"- {' — '.join(parts)}")
            if len(items) > 50:
                lines.append(f"- _(+{len(items) - 50} more)_")
            lines.append("")
        return "\n".join(lines)


def _module_referenced_in_docs(module_path: str, doc_scan: dict[str, dict]) -> bool:
    """Module mentioned in any doc's frontmatter source_files / wikilinks / code_refs?"""
    stem = Path(module_path).stem
    for doc, info in doc_scan.items():
        fm = info.get("frontmatter", {}) or {}
        sf = fm.get("source_files") or fm.get("sources") or []
        if isinstance(sf, str):
            sf = [sf]
        if any(module_path in str(s) or stem == Path(str(s)).stem for s in sf):
            return True
        for ref in info.get("code_refs", []):
            if module_path in ref or Path(ref).stem == stem:
                return True
        for wl in info.get("wikilinks", []):
            if wl == stem or wl.endswith(f"/{stem}"):
                return True
    return False


def detect(repo: Path, doc_root: Path | None = None) -> DriftReport:
    repo = repo.expanduser().resolve()
    doc_root = (doc_root or repo).expanduser().resolve()

    code = scan_code.scan_tree(repo)
    docs = scan_docs.scan_tree(doc_root)

    report = DriftReport(repo_root=str(repo), code_modules=len(code), doc_files=len(docs))

    # GAP: code without doc reference
    for mod_path, mod_info in code.items():
        # Only flag modules with public surface area
        has_public = mod_info["public_classes"] or mod_info["public_functions"]
        if not has_public:
            continue
        if not _module_referenced_in_docs(mod_path, docs):
            report.gap.append({"module": mod_path,
                               "public_count": len(mod_info["public_classes"]) + len(mod_info["public_functions"]),
                               "docstring": mod_info["docstring_first_line"]})

    # ORPHAN: doc code_refs pointing to non-existent files
    # Use filesystem (not just scan_code result) — tests/ are excluded from public-API scan
    # but still exist on disk and should NOT be flagged orphan.
    code_paths = set(code.keys())
    fs_paths: set[str] = set()
    fs_stems: set[str] = set()
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        if is_excluded(p, repo):
            continue
        rel = str(p.relative_to(repo))
        fs_paths.add(rel)
        fs_stems.add(p.stem)

    scanned_exts = {Path(p).suffix for p in code_paths}
    dominant_ext = max(scanned_exts, key=lambda e: sum(1 for p in code_paths if Path(p).suffix == e), default=".py") if scanned_exts else ".py"

    for doc, info in docs.items():
        if info.get("manual_edit"):
            continue
        for ref in info.get("code_refs", []):
            ref_path = ref.split(":")[0]
            ref_suffix = Path(ref_path).suffix
            if ref_path in fs_paths:
                continue
            # also accept partial matches (basename-only refs)
            if "/" not in ref_path and Path(ref_path).stem in fs_stems:
                continue
            # ignore foreign extensions
            if ref_suffix and ref_suffix not in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".sql"):
                continue
            if ref_suffix and ref_suffix != dominant_ext and ref_suffix in (".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".py"):
                if ref_suffix not in scanned_exts:
                    continue
            report.orphan.append({"doc": doc, "ref": ref})

    # SYMBOL DRIFT: doc backtick mentions of a symbol that exists in NO code module
    all_symbols: set[str] = set()
    for mod_info in code.values():
        all_symbols.update(mod_info["public_classes"])
        all_symbols.update(mod_info["public_functions"])

    for doc, info in docs.items():
        if info.get("manual_edit"):
            continue
        # Source files this doc claims to cover (per frontmatter)
        fm = info.get("frontmatter", {}) or {}
        claimed = fm.get("source_files") or fm.get("sources") or []
        if isinstance(claimed, str):
            claimed = [claimed]
        claimed_symbols: set[str] = set()
        for c in claimed:
            c_path = str(c)
            if c_path in code:
                claimed_symbols.update(code[c_path]["public_classes"])
                claimed_symbols.update(code[c_path]["public_functions"])
        # Only check symbol drift for docs that explicitly claim source files
        # (otherwise too noisy — natural-language docs mention many symbols loosely)
        if not claimed_symbols:
            continue
        for sym in info.get("symbol_mentions", []):
            # require PascalCase OR snake_case with ≥2 underscores (high-confidence identifiers)
            if not (re.match(r"^[A-Z][a-zA-Z0-9_]+$", sym) and len(sym) > 3) \
                    and not re.match(r"^[a-z]+(_[a-z0-9]+){2,}$", sym):
                continue
            if sym in all_symbols:
                continue
            if sym not in claimed_symbols:
                report.symbol_drift.append({"doc": doc, "symbol": sym, "claimed_files": claimed})

    # CLAIM DRIFT: signature mentioned in doc differs from code
    # Simple heuristic: scan doc body for `name(...)` patterns; compare to scan_code signatures
    SIG_IN_DOC_RE = re.compile(r"`([a-z_][a-z0-9_]+)\(([^)]*)\)`")
    for doc, info in docs.items():
        if info.get("manual_edit"):
            continue
        doc_path = doc_root / doc
        try:
            body = doc_path.read_text(errors="replace")
        except OSError as exc:
            print(f"drift: failed to read {doc_path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        for m in SIG_IN_DOC_RE.finditer(body):
            name, args_str = m.group(1), m.group(2).strip()
            # Find this symbol in any code module
            for mod_path, mod_info in code.items():
                if name in mod_info["signatures"]:
                    real_sig = mod_info["signatures"][name]
                    # Compare arg lists (simple: extract args portion)
                    real_args = real_sig[real_sig.index("(") + 1: real_sig.rindex(")")].strip()
                    # Strip type annotations + defaults for shallow compare
                    def _norm(s: str) -> str:
                        parts = [a.split(":")[0].split("=")[0].strip() for a in s.split(",") if a.strip()]
                        return ",".join(parts)
                    if _norm(args_str) != _norm(real_args):
                        report.claim_drift.append({
                            "doc": doc, "symbol": name,
                            "doc_says": f"{name}({args_str})",
                            "code_has": real_sig,
                            "module": mod_path,
                        })
                    break

    return report


def main(argv: list[str]) -> int:
    import argparse
    import json
    import sys
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--doc-root", type=Path, default=None)
    ap.add_argument("--format", choices=["json", "md"], default="md")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv[1:])
    report = detect(args.repo, args.doc_root)
    content = json.dumps(report.to_dict(), indent=2, ensure_ascii=False) if args.format == "json" else report.to_markdown()
    if args.out:
        args.out.write_text(content)
        print(f"wrote {args.out}")
    else:
        print(content)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv))
