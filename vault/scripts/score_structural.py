#!/usr/bin/env python3
"""
Structural quality scoring for NotebookLM-Archive vault.

10-dim rubric, 100pt total. Output: meta/score-state.json + stdout summary.

Usage:
    python3 score_structural.py <vault-path>
    python3 score_structural.py ~/Documents/Obsidian/NotebookLM-Archive
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import TextIO

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PATH = PLUGIN_ROOT / "templates" / "rubric.yaml"

_FALLBACK_MAX_PTS = {
    "graph_density": 15, "confidence_balance": 10, "concept_entity_depth": 10,
    "adr_pages": 10, "cross_vault": 10, "hot_cache": 10, "wiki_articles": 10,
    "bases": 5, "backlinks": 10, "conflict_dup": 10,
}


def _write_line(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")


def _emit(message: str) -> None:
    _write_line(sys.stdout, message)


def _warn(message: str) -> None:
    _write_line(sys.stderr, message)


def _load_max_pts() -> dict[str, int]:
    """Load per-dim max points from rubric.yaml; fallback to hardcoded defaults."""
    if not RUBRIC_PATH.exists():
        return dict(_FALLBACK_MAX_PTS)
    try:
        import yaml
    except ImportError as exc:
        _warn(f"score_structural: failed to load rubric {RUBRIC_PATH}: {type(exc).__name__}: {exc}")
        return dict(_FALLBACK_MAX_PTS)
    try:
        data = yaml.safe_load(RUBRIC_PATH.read_text()) or {}
        dims = (data.get("structural") or {}).get("dimensions") or {}
        out = {name: int(cfg.get("max", _FALLBACK_MAX_PTS.get(name, 10)))
               for name, cfg in dims.items()}
        for k, v in _FALLBACK_MAX_PTS.items():
            out.setdefault(k, v)
        return out
    except (OSError, yaml.YAMLError, AttributeError, TypeError, ValueError) as exc:
        _warn(f"score_structural: failed to load rubric {RUBRIC_PATH}: {type(exc).__name__}: {exc}")
        return dict(_FALLBACK_MAX_PTS)


def _load_categories(vault_root: Path) -> list[str]:
    cats_path = vault_root / "meta" / "categories.json"
    if cats_path.exists():
        return json.loads(cats_path.read_text())
    return [
        d.name for d in vault_root.iterdir()
        if d.is_dir() and (d / "raw").exists() and not d.name.startswith(".")
    ]


def _score_graph_density(vault_root: Path, cats: list[str]) -> tuple[float, str]:
    total_nodes = total_edges = 0
    hyperedge_cats = 0
    per_cat_dens: list[float] = []
    for c in cats:
        gpath = vault_root / c / "raw" / "graphify-out" / "graph.json"
        if not gpath.exists():
            continue
        g = json.loads(gpath.read_text())
        n_nodes = len(g.get("nodes", []))
        edges = g.get("links", g.get("edges", []))
        n_edges = len(edges)
        total_nodes += n_nodes
        total_edges += n_edges
        per_cat_dens.append(n_edges / max(n_nodes, 1))
        if g.get("hyperedges"):
            hyperedge_cats += 1
    overall_dens = total_edges / max(total_nodes, 1)
    cats_above_15 = sum(1 for d in per_cat_dens if d >= 1.5)
    score = 0.0
    score += 10 if overall_dens >= 1.5 else 6 * overall_dens / 1.5
    score += 5 if hyperedge_cats == len(cats) else 3 * hyperedge_cats / max(len(cats), 1)
    detail = (
        f"{total_nodes}n/{total_edges}e dens={overall_dens:.2f} "
        f"hyper={hyperedge_cats}/{len(cats)} cats≥1.5: {cats_above_15}/{len(cats)}"
    )
    return round(min(15, score), 1), detail


def _score_confidence_balance(vault_root: Path, cats: list[str]) -> tuple[float, str]:
    in_band_cats = 0
    for c in cats:
        gpath = vault_root / c / "raw" / "graphify-out" / "graph.json"
        if not gpath.exists():
            continue
        g = json.loads(gpath.read_text())
        edges = g.get("links", g.get("edges", []))
        if not edges:
            continue
        conf = Counter(e.get("confidence", "?") for e in edges)
        ext = conf.get("EXTRACTED", 0) / len(edges)
        inf = conf.get("INFERRED", 0) / len(edges)
        amb = conf.get("AMBIGUOUS", 0) / len(edges)
        if ext >= 0.10 and 0.40 <= inf <= 0.80 and amb <= 0.15:
            in_band_cats += 1
    score = round(10 * in_band_cats / max(len(cats), 1), 1)
    return score, f"{in_band_cats}/{len(cats)} in band"


def _score_concept_entity_depth(vault_root: Path, cats: list[str]) -> tuple[float, str]:
    depth_ok = 0
    for c in cats:
        con = len([f for f in (vault_root / c / "concepts").glob("*.md") if f.name != "_index.md"]) \
              if (vault_root / c / "concepts").exists() else 0
        ent = len([f for f in (vault_root / c / "entities").glob("*.md") if f.name != "_index.md"]) \
              if (vault_root / c / "entities").exists() else 0
        if con >= 3 and ent >= 3:
            depth_ok += 1
    score = round(10 * depth_ok / max(len(cats), 1), 1)
    return score, f"{depth_ok}/{len(cats)} cats ≥3 concepts & entities"


def _score_adr_pages(vault_root: Path, cats: list[str]) -> tuple[float, str]:
    adr_cats = 0
    for c in cats:
        dec = vault_root / c / "decisions"
        if not dec.exists():
            continue
        adrs = [f for f in dec.glob("adr-*.md") if f.name != "_index.md"]
        if len(adrs) >= 2:
            adr_cats += 1
    score = round(min(10, 10 * adr_cats / 3), 1)
    return score, f"{adr_cats} cats have ≥2 ADRs"


def _score_cross_vault(vault_root: Path) -> tuple[float, str]:
    cv_path = vault_root / "meta" / "cross-vault-links.md"
    if not cv_path.exists():
        return 0.0, "cross-vault-links.md missing"
    cv = cv_path.read_text()
    real_links = re.findall(r"\[\[\.\./\.\./[A-Za-z][^\]|#]+", cv)
    verified = 0
    for link in real_links[:30]:
        rel = link[2:]
        target = (cv_path.parent / rel).resolve()
        if target.with_suffix(".md").exists() or target.exists():
            verified += 1
    score = round(10 * verified / max(min(30, len(real_links)), 1), 1) if real_links else 0.0
    detail = f"{verified}/{min(30, len(real_links))} cross-vault links verified ({len(real_links)} total)"
    return score, detail


def _score_hot_cache(vault_root: Path, cats: list[str]) -> tuple[float, str]:
    sections = ["God Nodes", "Cross-bridges", "Source Files", "Quick Questions", "Cross-vault"]
    hot_filled = 0
    for c in cats:
        hpath = vault_root / c / "hot.md"
        if not hpath.exists():
            continue
        text = hpath.read_text()
        if sum(1 for s in sections if s in text) >= 4:
            hot_filled += 1
    score = round(10 * hot_filled / max(len(cats), 1), 1)
    return score, f"{hot_filled}/{len(cats)} hot.md structured"


def _score_wiki_articles(vault_root: Path, cats: list[str]) -> tuple[float, str]:
    pass_articles = total_articles = 0
    for c in cats:
        wiki_dir = vault_root / c / "raw" / "graphify-out" / "wiki"
        if not wiki_dir.exists():
            continue
        for f in wiki_dir.glob("*.md"):
            if f.name == "index.md":
                continue
            total_articles += 1
            text = f.read_text()
            src_match = re.search(r"## Source Files\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
            src_count = len(re.findall(r"^- ", src_match.group(1), re.MULTILINE)) if src_match else 0
            has_rel = "## Relationships" in text
            if src_count >= 3 and has_rel:
                pass_articles += 1
    score = round(10 * pass_articles / max(total_articles, 1), 1) if total_articles else 0.0
    return score, f"{pass_articles}/{total_articles} articles pass"


def _score_bases(vault_root: Path) -> tuple[float, str]:
    bases = list(vault_root.rglob("*.base"))
    score = 5.0 if len(bases) >= 5 else round(5 * len(bases) / 5, 1)
    return score, f"{len(bases)} .base files"


def _build_inbound_map(authored_md: list[Path]) -> dict[str, int]:
    inbound: dict[str, int] = {f.stem: 0 for f in authored_md}
    for f in authored_md:
        for m in re.finditer(r"\[\[([^\]|#]+)", f.read_text()):
            t = m.group(1).split("/")[-1].strip()
            if t.endswith(".md"):
                t = t[:-3]
            if t in inbound:
                inbound[t] += 1
    return inbound


def _score_backlinks(vault_root: Path) -> tuple[float, str]:
    authored_md = [
        f for f in vault_root.rglob("*.md")
        if "graphify-out" not in str(f) and "/raw/" not in str(f) and f.name != "_index.md"
    ]
    inbound = _build_inbound_map(authored_md)
    source_pages = [
        f.stem for f in vault_root.rglob("sources/*.md")
        if f.name != "_index.md"
    ]
    weak = sum(1 for s in source_pages if inbound.get(s, 0) < 2)
    coverage = 1 - weak / max(len(source_pages), 1)
    score = round(10 * coverage, 1)
    return score, f"{len(source_pages) - weak}/{len(source_pages)} sources ≥2 inbound"


def _score_conflict_dup(vault_root: Path, cats: list[str]) -> tuple[float, str]:
    scaffolding = {"index", "hot", "log", "overview"}
    spurious_dups: dict[str, int] = {}
    for cat in cats:
        cat_root = vault_root / cat
        if not cat_root.is_dir():
            continue
        cat_stems = [
            f.stem for f in cat_root.rglob("*.md")
            if "graphify-out" not in str(f) and "/raw/" not in str(f) and f.stem != "_index"
        ]
        for stem, count in Counter(cat_stems).items():
            if count > 1 and stem not in scaffolding:
                spurious_dups[f"{cat}/{stem}"] = count
    score = 10.0 if not spurious_dups else max(0, 10 - len(spurious_dups))
    return score, f"{len(spurious_dups)} spurious dup stems"


def score_vault(vault_root: Path) -> dict:
    """Score vault content against the rubric."""
    cats = _load_categories(vault_root)

    scores: dict[str, float] = {}
    details: dict[str, str] = {}

    scores["graph_density"], details["graph_density"] = _score_graph_density(vault_root, cats)
    scores["confidence_balance"], details["confidence_balance"] = _score_confidence_balance(vault_root, cats)
    scores["concept_entity_depth"], details["concept_entity_depth"] = _score_concept_entity_depth(vault_root, cats)
    scores["adr_pages"], details["adr_pages"] = _score_adr_pages(vault_root, cats)
    scores["cross_vault"], details["cross_vault"] = _score_cross_vault(vault_root)
    scores["hot_cache"], details["hot_cache"] = _score_hot_cache(vault_root, cats)
    scores["wiki_articles"], details["wiki_articles"] = _score_wiki_articles(vault_root, cats)
    scores["bases"], details["bases"] = _score_bases(vault_root)
    scores["backlinks"], details["backlinks"] = _score_backlinks(vault_root)
    scores["conflict_dup"], details["conflict_dup"] = _score_conflict_dup(vault_root, cats)

    total = min(100, sum(scores.values()))
    return {
        "total": round(total, 1),
        "scores": scores,
        "details": details,
        "categories": cats,
    }


def main() -> None:
    """Run the score-structural command-line entry point."""
    if len(sys.argv) < 2:
        _warn("Usage: score_structural.py <vault-path>")
        sys.exit(1)
    vault = Path(sys.argv[1]).expanduser().resolve()
    if not vault.exists():
        _warn(f"Vault not found: {vault}")
        sys.exit(1)

    state = score_vault(vault)

    _emit("=" * 60)
    _emit(f"Structural Score: {state['total']:.1f}/100")
    _emit("=" * 60)
    max_pts = _load_max_pts()
    for k, v in state["scores"].items():
        _emit(f"  {k:25} {v:5.1f}/{max_pts.get(k, 10):2} — {state['details'][k]}")

    out = vault / "meta" / "score-state.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    _emit(f"\nSaved {out.relative_to(vault)}")


if __name__ == "__main__":
    main()
