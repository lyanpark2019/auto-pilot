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

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PATH = PLUGIN_ROOT / "templates" / "rubric.yaml"

_FALLBACK_MAX_PTS = {
    "graph_density": 15, "confidence_balance": 10, "concept_entity_depth": 10,
    "adr_pages": 10, "cross_vault": 10, "hot_cache": 10, "wiki_articles": 10,
    "bases": 5, "backlinks": 10, "conflict_dup": 10,
}


def _load_max_pts() -> dict[str, int]:
    """Load per-dim max points from rubric.yaml; fallback to hardcoded defaults."""
    if not RUBRIC_PATH.exists():
        return dict(_FALLBACK_MAX_PTS)
    try:
        import yaml
        data = yaml.safe_load(RUBRIC_PATH.read_text()) or {}
        dims = (data.get("structural") or {}).get("dimensions") or {}
        out = {name: int(cfg.get("max", _FALLBACK_MAX_PTS.get(name, 10)))
               for name, cfg in dims.items()}
        # Backfill any missing dim
        for k, v in _FALLBACK_MAX_PTS.items():
            out.setdefault(k, v)
        return out
    except Exception as exc:
        print(f"score_structural: failed to load rubric {RUBRIC_PATH}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return dict(_FALLBACK_MAX_PTS)


def score_vault(vault_root: Path) -> dict:
    cats_path = vault_root / "meta" / "categories.json"
    if cats_path.exists():
        CATS = json.loads(cats_path.read_text())
    else:
        # discover from directory structure
        CATS = [d.name for d in vault_root.iterdir()
                if d.is_dir() and (d / "raw").exists() and not d.name.startswith(".")]

    scores: dict[str, float] = {}
    details: dict[str, str] = {}

    # 1. Graph extraction (15pt — density + hyperedges)
    total_nodes = total_edges = total_amb = total_files = 0
    hyperedge_cats = 0
    per_cat_dens = []
    for c in CATS:
        gpath = vault_root / c / "raw" / "graphify-out" / "graph.json"
        if not gpath.exists():
            continue
        g = json.loads(gpath.read_text())
        n_files = len(list((vault_root / c / "raw").glob("*.md")))
        n_nodes = len(g.get("nodes", []))
        edges = g.get("links", g.get("edges", []))
        n_edges = len(edges)
        n_amb = sum(1 for e in edges if e.get("confidence") == "AMBIGUOUS")
        total_nodes += n_nodes
        total_edges += n_edges
        total_amb += n_amb
        total_files += n_files
        per_cat_dens.append(n_edges / max(n_nodes, 1))
        if g.get("hyperedges"):
            hyperedge_cats += 1
    overall_dens = total_edges / max(total_nodes, 1)
    cats_above_15 = sum(1 for d in per_cat_dens if d >= 1.5)
    score = 0
    score += 10 if overall_dens >= 1.5 else 6 * overall_dens / 1.5
    score += 5 if hyperedge_cats == len(CATS) else 3 * hyperedge_cats / max(len(CATS), 1)
    scores["graph_density"] = round(min(15, score), 1)
    details["graph_density"] = (
        f"{total_nodes}n/{total_edges}e dens={overall_dens:.2f} "
        f"hyper={hyperedge_cats}/{len(CATS)} cats≥1.5: {cats_above_15}/{len(CATS)}"
    )

    # 2. Confidence balance (10pt)
    in_band_cats = 0
    for c in CATS:
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
    scores["confidence_balance"] = round(10 * in_band_cats / max(len(CATS), 1), 1)
    details["confidence_balance"] = f"{in_band_cats}/{len(CATS)} in band"

    # 3. Concept/Entity depth (10pt)
    depth_ok = 0
    for c in CATS:
        con = len([f for f in (vault_root / c / "concepts").glob("*.md") if f.name != "_index.md"]) \
              if (vault_root / c / "concepts").exists() else 0
        ent = len([f for f in (vault_root / c / "entities").glob("*.md") if f.name != "_index.md"]) \
              if (vault_root / c / "entities").exists() else 0
        if con >= 3 and ent >= 3:
            depth_ok += 1
    scores["concept_entity_depth"] = round(10 * depth_ok / max(len(CATS), 1), 1)
    details["concept_entity_depth"] = f"{depth_ok}/{len(CATS)} cats ≥3 concepts & entities"

    # 4. ADR (10pt — sportic/pickl/agri or any 3 cats)
    adr_cats = 0
    for c in CATS:
        dec = vault_root / c / "decisions"
        if not dec.exists():
            continue
        adrs = [f for f in dec.glob("adr-*.md") if f.name != "_index.md"]
        if len(adrs) >= 2:
            adr_cats += 1
    scores["adr_pages"] = round(min(10, 10 * adr_cats / 3), 1)  # 3 cats with ADRs = full
    details["adr_pages"] = f"{adr_cats} cats have ≥2 ADRs"

    # 5. Cross-vault wikilinks (10pt)
    cv_path = vault_root / "meta" / "cross-vault-links.md"
    if cv_path.exists():
        cv = cv_path.read_text()
        # count [[../../<Vault>/wiki/...]] entries
        real_links = re.findall(r"\[\[\.\./\.\./[A-Za-z][^\]|#]+", cv)
        # verify file existence (sample)
        verified = 0
        for link in real_links[:30]:
            rel = link[2:]
            target = (cv_path.parent / rel).resolve()
            # try .md
            if target.with_suffix(".md").exists() or target.exists():
                verified += 1
        scores["cross_vault"] = round(10 * verified / max(min(30, len(real_links)), 1), 1) if real_links else 0
        details["cross_vault"] = f"{verified}/{min(30, len(real_links))} cross-vault links verified ({len(real_links)} total)"
    else:
        scores["cross_vault"] = 0
        details["cross_vault"] = "cross-vault-links.md missing"

    # 6. Hot cache (10pt)
    hot_filled = 0
    for c in CATS:
        hpath = vault_root / c / "hot.md"
        if not hpath.exists():
            continue
        text = hpath.read_text()
        sections = ["God Nodes", "Cross-bridges", "Source Files", "Quick Questions", "Cross-vault"]
        if sum(1 for s in sections if s in text) >= 4:
            hot_filled += 1
    scores["hot_cache"] = round(10 * hot_filled / max(len(CATS), 1), 1)
    details["hot_cache"] = f"{hot_filled}/{len(CATS)} hot.md structured"

    # 7. Wiki community articles (10pt)
    pass_articles = 0
    total_articles = 0
    for c in CATS:
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
    scores["wiki_articles"] = round(10 * pass_articles / max(total_articles, 1), 1) if total_articles else 0
    details["wiki_articles"] = f"{pass_articles}/{total_articles} articles pass"

    # 8. Obsidian Bases (5pt)
    bases = list(vault_root.rglob("*.base"))
    scores["bases"] = 5 if len(bases) >= 5 else round(5 * len(bases) / 5, 1)
    details["bases"] = f"{len(bases)} .base files"

    # 9. Backlinks coverage (10pt) — sample 15 source pages
    authored_md = [
        f for f in vault_root.rglob("*.md")
        if "graphify-out" not in str(f) and "/raw/" not in str(f) and f.name != "_index.md"
    ]
    inbound = {f.stem: 0 for f in authored_md}
    for f in authored_md:
        for m in re.finditer(r"\[\[([^\]|#]+)", f.read_text()):
            t = m.group(1).split("/")[-1].strip()
            if t.endswith(".md"):
                t = t[:-3]
            if t in inbound:
                inbound[t] += 1
    source_pages = [
        f.stem for f in vault_root.rglob("sources/*.md")
        if f.name != "_index.md"
    ]
    weak = sum(1 for s in source_pages if inbound.get(s, 0) < 2)
    coverage = 1 - weak / max(len(source_pages), 1)
    scores["backlinks"] = round(10 * coverage, 1)
    details["backlinks"] = f"{len(source_pages) - weak}/{len(source_pages)} sources ≥2 inbound"

    # 10. Conflict/dup (10pt) — duplicate stems WITHIN the same category only.
    # Cross-category same-stem files (e.g. concepts/auth.md per cat) are legitimate.
    scaffolding = {"index", "hot", "log", "overview"}
    spurious_dups: dict[str, int] = {}
    for cat in CATS:
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
    if not spurious_dups:
        scores["conflict_dup"] = 10
    else:
        scores["conflict_dup"] = max(0, 10 - len(spurious_dups))
    details["conflict_dup"] = f"{len(spurious_dups)} spurious dup stems"

    total = min(100, sum(scores.values()))

    state = {
        "total": round(total, 1),
        "scores": scores,
        "details": details,
        "categories": CATS,
    }
    return state


def main():
    if len(sys.argv) < 2:
        print("Usage: score_structural.py <vault-path>", file=sys.stderr)
        sys.exit(1)
    vault = Path(sys.argv[1]).expanduser().resolve()
    if not vault.exists():
        print(f"Vault not found: {vault}", file=sys.stderr)
        sys.exit(1)

    state = score_vault(vault)

    print("=" * 60)
    print(f"Structural Score: {state['total']:.1f}/100")
    print("=" * 60)
    max_pts = _load_max_pts()
    for k, v in state["scores"].items():
        print(f"  {k:25} {v:5.1f}/{max_pts.get(k, 10):2} — {state['details'][k]}")

    out = vault / "meta" / "score-state.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    print(f"\nSaved {out.relative_to(vault)}")


if __name__ == "__main__":
    main()
