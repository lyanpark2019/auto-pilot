#!/usr/bin/env python3
"""Export updated project docs to 3 destinations.

Destinations (all upsert — update existing, create if missing):
- obsidian   : Obsidian vault at ~/Documents/Obsidian/<project>/ (override via --obsidian-path)
- notebooklm : NotebookLM notebook named <project> (override via --notebook-name)
- graphify   : graphify graph at <project>/.vault-builder/graphify-out/

Each exporter is idempotent:
- Obsidian: copies docs/, adds wikilinks/frontmatter, preserves existing manual_edit pages
- NotebookLM: looks up existing notebook by name; creates if absent; syncs sources
- graphify: runs `graphify build` on docs/ → reuses existing graph if up-to-date
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):  # script mode (python3 vault/pipeline/export.py …)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_OBSIDIAN_ROOT = Path(os.environ.get("VB_OBSIDIAN_ROOT", str(Path.home() / "Documents" / "Obsidian")))
GRAPHIFY_BIN = os.environ.get("GRAPHIFY_BIN", str(Path.home() / ".local" / "bin" / "graphify"))


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError as e:
        return -2, "", str(e)


# ──── Obsidian exporter ───────────────────────────────────────────────────────


def export_obsidian(repo: Path, vault_root: Path | None = None,
                    doc_root: Path | None = None, project_name: str | None = None) -> dict:
    """Upsert docs into Obsidian vault.

    Existing vault: preserve manual_edit pages, replace auto-managed ones.
    Missing vault: create from scratch + index.md.
    """
    repo = repo.expanduser().resolve()
    doc_root = (doc_root or (repo / "docs")).expanduser().resolve()
    project_name = project_name or repo.name
    vault = (vault_root or DEFAULT_OBSIDIAN_ROOT) / project_name
    vault = vault.expanduser().resolve()

    created = not vault.exists()
    vault.mkdir(parents=True, exist_ok=True)

    # Bootstrap .obsidian/ config so Obsidian app recognizes folder as a vault
    obsidian_dir = vault / ".obsidian"
    if not obsidian_dir.exists():
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        # Minimal config — Obsidian populates the rest on first open
        (obsidian_dir / "app.json").write_text("{}")
        (obsidian_dir / "appearance.json").write_text("{}")
        (obsidian_dir / "core-plugins.json").write_text(
            '["file-explorer","global-search","switcher","graph","backlink",'
            '"canvas","outgoing-link","tag-pane","page-preview","daily-notes",'
            '"templates","outline","word-count","file-recovery"]'
        )

    copied = 0
    skipped_manual = 0
    if doc_root.exists():
        for src in doc_root.rglob("*.md"):
            rel = src.relative_to(doc_root)
            tgt = vault / rel
            tgt.parent.mkdir(parents=True, exist_ok=True)
            if tgt.exists():
                # preserve manual_edit pages
                existing = tgt.read_text(errors="replace")
                fm_match = re.match(r"^---\n(.*?)\n---\n", existing, re.DOTALL)
                if fm_match and re.search(r"manual_edit:\s*true", fm_match.group(1), re.IGNORECASE):
                    skipped_manual += 1
                    continue
            shutil.copy2(src, tgt)
            copied += 1

    # Also copy top-level docs (README.md, CLAUDE.md, etc) to vault root
    for top in ("README.md", "CLAUDE.md", "AGENTS.md", "ARCHITECTURE.md", "CHANGELOG.md"):
        src = repo / top
        if src.exists():
            tgt = vault / top
            if tgt.exists() and re.search(r"manual_edit:\s*true", tgt.read_text(errors="replace") or "", re.IGNORECASE):
                skipped_manual += 1
                continue
            shutil.copy2(src, tgt)
            copied += 1

    # Generate or refresh index.md
    pages = [p.relative_to(vault) for p in vault.rglob("*.md")
             if not str(p.relative_to(vault)).startswith(".")]
    index_path = vault / "index.md"
    if not index_path.exists() or "auto-generated" in index_path.read_text(errors="replace"):
        lines = [
            "---",
            f"type: index",
            f"project: {project_name}",
            f"auto-generated: {time.strftime('%Y-%m-%d')}",
            "---",
            "",
            f"# {project_name}",
            "",
            f"## Pages ({len(pages)})",
            "",
        ]
        for p in sorted(pages):
            if p.name == "index.md":
                continue
            lines.append(f"- [[{str(p)[:-3]}]]")
        index_path.write_text("\n".join(lines))

    return {
        "destination": "obsidian",
        "vault": str(vault),
        "created_new": created,
        "pages_copied": copied,
        "manual_pages_preserved": skipped_manual,
    }


# ──── NotebookLM exporter ─────────────────────────────────────────────────────


def export_notebooklm(repo: Path, doc_root: Path | None = None,
                      project_name: str | None = None, max_sources: int = 50) -> dict:
    """Upsert NotebookLM notebook.

    Lookup by name; if missing, create. Then sync sources (markdown files).
    Existing sources matched by title; new sources added; obsolete removed.
    """
    repo = repo.expanduser().resolve()
    doc_root = (doc_root or (repo / "docs")).expanduser().resolve()
    project_name = project_name or repo.name

    # List existing notebooks
    rc, out, err = _run(["notebooklm", "list", "--json"])
    if rc < 0:
        return {"destination": "notebooklm", "error": f"notebooklm CLI unavailable: {err}", "skipped": True}
    if rc != 0:
        return {"destination": "notebooklm", "error": f"list failed: {err}", "skipped": True}

    try:
        notebooks = json.loads(out).get("notebooks", [])
    except json.JSONDecodeError as e:
        return {"destination": "notebooklm", "error": f"parse failed: {e}", "skipped": True}

    notebook = next((nb for nb in notebooks if nb.get("title") == project_name), None)
    created = False
    if notebook is None:
        rc, out, err = _run(["notebooklm", "create", "--title", project_name, "--json"])
        if rc != 0:
            return {"destination": "notebooklm", "error": f"create failed: {err}", "skipped": True}
        try:
            notebook = json.loads(out).get("notebook") or json.loads(out)
        except json.JSONDecodeError:
            notebook = None
        if not notebook:
            return {"destination": "notebooklm", "error": "create returned no notebook", "skipped": True}
        created = True

    nb_id = notebook["id"]

    # Collect candidate source files (top-level + docs/)
    sources: list[Path] = []
    for top in ("README.md", "CLAUDE.md", "AGENTS.md", "ARCHITECTURE.md"):
        p = repo / top
        if p.exists():
            sources.append(p)
    if doc_root.exists():
        sources.extend(sorted(doc_root.rglob("*.md")))
    sources = sources[:max_sources]

    # Get existing sources
    rc, out, _ = _run(["notebooklm", "source", "list", "--notebook", nb_id, "--json"])
    existing_titles = set()
    if rc == 0:
        try:
            existing_titles = {s.get("title", "") for s in json.loads(out).get("sources", [])}
        except json.JSONDecodeError as exc:
            print(f"export: failed to parse existing sources list: {type(exc).__name__}: {exc}", file=sys.stderr)

    added = 0
    for src in sources:
        title = str(src.relative_to(repo))
        if title in existing_titles:
            continue
        rc, _, err = _run(["notebooklm", "source", "add", "--notebook", nb_id,
                           "--title", title, "--file", str(src)], timeout=60)
        if rc == 0:
            added += 1

    return {
        "destination": "notebooklm",
        "notebook_id": nb_id,
        "notebook_title": project_name,
        "created_new": created,
        "sources_added": added,
        "total_sources_attempted": len(sources),
    }


# ──── graphify exporter ───────────────────────────────────────────────────────


def export_graphify(repo: Path, doc_root: Path | None = None) -> dict:
    repo = repo.expanduser().resolve()
    doc_root = (doc_root or (repo / "docs")).expanduser().resolve()
    out_dir = repo / ".vault-builder" / "graphify-out"
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    if not Path(GRAPHIFY_BIN).exists():
        return {"destination": "graphify", "error": f"graphify not found: {GRAPHIFY_BIN}", "skipped": True}

    if not doc_root.exists():
        return {"destination": "graphify", "error": f"doc_root missing: {doc_root}", "skipped": True}

    # Current graphify CLI uses `extract`; the legacy `build` verb was removed.
    rc, out, err = _run(
        [GRAPHIFY_BIN, "extract", str(doc_root), "--no-cluster", "--out", str(out_dir.parent)],
        timeout=1800,
    )
    return {
        "destination": "graphify",
        "out": str(out_dir),
        "rc": rc,
        "stdout_tail": out.strip().splitlines()[-3:] if out else [],
        "stderr_tail": err.strip().splitlines()[-3:] if err else [],
    }


def export_bases(repo: Path, vault_root: Path | None = None,
                 project_name: str | None = None) -> dict:
    """Emit kepano `.base` dashboards under the Obsidian vault."""
    # Local import to keep optional. Dual-mode: relative when imported as a
    # package, absolute via the __package__ sys.path guard in script mode
    # (a bare relative import here broke `python3 pipeline/export.py --export bases`).
    if __package__:
        from .bases import generate_bases
    else:
        from pipeline.bases import generate_bases

    repo = repo.expanduser().resolve()
    vault_root = (vault_root or DEFAULT_OBSIDIAN_ROOT).expanduser().resolve()
    project = project_name or repo.name
    vault = vault_root / project
    if not (vault / "wikitree").exists():
        return {"destination": "bases", "skipped": True,
                "reason": f"vault missing wikitree/: {vault}"}
    written = generate_bases(vault)
    return {
        "destination": "bases",
        "vault": str(vault),
        "files": [str(p) for p in written],
    }


def export_canvas(repo: Path, vault_root: Path | None = None,
                  project_name: str | None = None) -> dict:
    """Emit graph-hub canvas under the Obsidian vault."""
    # Dual-mode import — same rationale as export_bases.
    if __package__:
        from .canvas import emit_graph_canvas
    else:
        from pipeline.canvas import emit_graph_canvas

    repo = repo.expanduser().resolve()
    vault_root = (vault_root or DEFAULT_OBSIDIAN_ROOT).expanduser().resolve()
    project = project_name or repo.name
    vault = vault_root / project
    out = emit_graph_canvas(vault)
    if out is None:
        return {"destination": "canvas", "skipped": True,
                "reason": f"graph.json missing for vault {vault}"}
    return {"destination": "canvas", "vault": str(vault), "file": str(out)}


def auto_graphify_update(repo: Path, global_tag: str | None = None,
                          merge_global: bool = True) -> dict:
    """Run graphify update on repo + optional global graph merge.

    Returns a dict describing each step's rc. Skips silently when graphify CLI
    is unavailable. Always uses the current `update`/`extract`/`global add`
    contract (not the removed `build`).
    """
    repo = repo.expanduser().resolve()
    if not Path(GRAPHIFY_BIN).exists():
        return {"step": "auto-graphify", "skipped": True,
                "reason": f"graphify not found: {GRAPHIFY_BIN}"}
    graph_json = repo / "graphify-out" / "graph.json"
    if graph_json.exists():
        rc, out, err = _run([GRAPHIFY_BIN, "update", str(repo)], timeout=600)
    else:
        rc, out, err = _run([GRAPHIFY_BIN, "extract", str(repo), "--no-cluster"], timeout=1800)
    result = {"step": "auto-graphify", "rc": rc,
              "stdout_tail": out.strip().splitlines()[-3:] if out else [],
              "stderr_tail": err.strip().splitlines()[-3:] if err else []}
    if rc != 0 or not merge_global or not graph_json.exists():
        return result
    tag = global_tag or repo.name
    g_rc, g_out, g_err = _run([GRAPHIFY_BIN, "global", "add", str(graph_json),
                                "--as", tag], timeout=120)
    result["global_add"] = {"rc": g_rc, "tag": tag,
                            "stdout_tail": g_out.strip().splitlines()[-3:] if g_out else []}
    return result


# ──── Driver ──────────────────────────────────────────────────────────────────


DESTINATIONS = {
    "obsidian": export_obsidian,
    "notebooklm": export_notebooklm,
    "graphify": export_graphify,
    "bases": export_bases,
    "canvas": export_canvas,
}


def export_all(repo: Path, destinations: list[str], **opts) -> dict:
    source_adapter = opts.pop("source_adapter", None)
    if source_adapter is None:
        state_file = Path(repo) / ".vault-builder" / "state.json"
        if state_file.exists():
            try:
                source_adapter = json.loads(state_file.read_text()).get("source_adapter")
            except Exception as exc:
                print(f"export: failed to read source_adapter from {state_file}: {type(exc).__name__}: {exc}", file=sys.stderr)
                source_adapter = None
    results = {}
    for d in destinations:
        if d == "notebooklm" and source_adapter == "notebooklm":
            results[d] = {
                "destination": "notebooklm",
                "skipped": True,
                "reason": "source_adapter == notebooklm; skipping reverse push to avoid duplicating sources.",
            }
            continue
        fn = DESTINATIONS.get(d)
        if not fn:
            results[d] = {"error": f"unknown destination: {d}", "failed": True}
            continue
        try:
            results[d] = fn(repo, **{k: v for k, v in opts.items() if k in fn.__code__.co_varnames})
        except Exception as e:
            print(f"export: destination={d} error_type={type(e).__name__}: {e}", file=sys.stderr)
            results[d] = {"destination": d, "error": str(e), "failed": True}
    return results


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--export", default="obsidian,notebooklm,graphify",
                    help="Comma-separated destinations (default: obsidian,notebooklm,graphify; "
                         "add 'bases' or 'canvas' for kepano dashboards / graph canvas)")
    ap.add_argument("--doc-root", type=Path, default=None)
    ap.add_argument("--obsidian-path", type=Path, default=None)
    ap.add_argument("--project-name", default=None)
    ap.add_argument("--source", default=None,
                    help="Source adapter that built the vault (e.g. notebooklm). When set, "
                         "the matching destination is auto-skipped to avoid reverse push.")
    ap.add_argument("--auto-graphify", action="store_true",
                    help="run graphify update + global add after exports")
    ap.add_argument("--global-tag", default=None,
                    help="repo tag for graphify global graph (default: repo dir name)")
    ap.add_argument("--no-global", action="store_true",
                    help="skip global graph merge when --auto-graphify set")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv[1:])

    dests = [d.strip() for d in args.export.split(",") if d.strip()]
    opts = {}
    if args.doc_root:
        opts["doc_root"] = args.doc_root
    if args.obsidian_path:
        opts["vault_root"] = args.obsidian_path
    if args.project_name:
        opts["project_name"] = args.project_name
    if args.source:
        opts["source_adapter"] = args.source

    results = export_all(args.repo, dests, **opts)
    if args.auto_graphify:
        results["auto_graphify"] = auto_graphify_update(
            args.repo,
            global_tag=args.global_tag,
            merge_global=not args.no_global,
        )
    content = json.dumps({"repo": str(args.repo.resolve()), "exports": results}, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(content)
        print(f"wrote {args.out}")
    else:
        print(content)
    # Surface real failures (exceptions / unknown destinations) as a non-zero
    # exit; graceful skips (missing CLI / inputs, marked "skipped") stay rc=0.
    failed = sorted(
        d for d, r in results.items()
        if isinstance(r, dict) and (r.get("failed") or (r.get("error") and not r.get("skipped")))
    )
    if failed:
        print(f"EXPORT FAILED for destination(s): {', '.join(failed)} — see report above", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
