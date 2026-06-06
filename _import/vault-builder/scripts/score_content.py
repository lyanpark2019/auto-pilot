#!/usr/bin/env python3
"""
Content accuracy scoring for NotebookLM-Archive vault.

Separate from structural score. 100pt, 7 dims focused on factual correctness:

1. Edge factual correctness (30) — sample N edges, check label token co-occurrence in source raw md
2. Concept page accuracy (20) — concept summary claims supported by source
3. ADR fidelity (15) — ADR content traces to source
4. Community label fit (10) — label matches member node theme
5. Cross-vault target relevance (10) — `real` flagged sibling pages share topic
6. Hot cache god_nodes citation accuracy (5)
7. Hallucination detection (10) — unsupported claims in worker-generated pages

Usage: python3 score_content.py <vault-path> [--sample-edges N] [--strict]

Note: This script provides a heuristic baseline. Full content audit needs the
content-fact-checker agent for semantic verification beyond token overlap.
"""

import json
import re
import sys
import random
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
RUBRIC_PATH = PLUGIN_ROOT / "templates" / "rubric.yaml"

_FALLBACK_MAX_PTS = {
    "edge_fact": 30, "concept_accuracy": 20, "adr_fidelity": 15,
    "label_fit": 10, "cross_vault_relevance": 10, "hot_citation": 5,
    "non_hallucinated": 10,
}


def _load_max_pts() -> dict[str, int]:
    if not RUBRIC_PATH.exists():
        return dict(_FALLBACK_MAX_PTS)
    try:
        import yaml
        data = yaml.safe_load(RUBRIC_PATH.read_text()) or {}
        dims = (data.get("content") or {}).get("dimensions") or {}
        out = {name: int(cfg.get("max", _FALLBACK_MAX_PTS.get(name, 10)))
               for name, cfg in dims.items()}
        for k, v in _FALLBACK_MAX_PTS.items():
            out.setdefault(k, v)
        return out
    except Exception:
        return dict(_FALLBACK_MAX_PTS)


def edge_token_check(vault: Path, cats: list, sample_n: int = 30) -> tuple[int, int, list]:
    """Sample N edges, check both label tokens appear in same raw source md."""
    rng = random.Random(42)
    sampled = []
    if not cats:
        return 0, 0, []
    per_cat = max(1, sample_n // len(cats) + 1)
    for c in cats:
        gpath = vault / c / "raw" / "graphify-out" / "graph.json"
        if not gpath.exists():
            continue
        g = json.loads(gpath.read_text())
        label = {n["id"]: n["label"] for n in g["nodes"]}
        edges = g.get("links", [])
        rng.shuffle(edges)
        # take INFERRED + AMBIGUOUS for verification (EXTRACTED already grounded)
        candidates = [e for e in edges if e.get("confidence") in ("INFERRED", "AMBIGUOUS")]
        sampled += [(c, e, label.get(e["source"], ""), label.get(e["target"], ""))
                    for e in candidates[:per_cat]]
    sampled = sampled[:sample_n]

    # cache raw text per cat
    raw_text = {}
    for c in cats:
        raw_text[c] = " ".join(
            f.read_text().lower() for f in (vault / c / "raw").glob("*.md")
        )

    def _tokens(label: str) -> list[str]:
        out = []
        for w in re.split(r"[\s\-/_·,()\[\]]+", label.lower()):
            if not w:
                continue
            is_cjk = any(
                "一" <= ch <= "鿿"  # CJK Unified Ideographs
                or "぀" <= ch <= "ヿ"  # Hiragana + Katakana
                or "가" <= ch <= "힯"  # Hangul Syllables
                for ch in w
            )
            if is_cjk and len(w) >= 2:
                out.append(w)
            elif not is_cjk and len(w) > 2:
                out.append(w)
        return out

    passed = 0
    failed_examples = []
    for c, e, s_lbl, t_lbl in sampled:
        s_tokens = _tokens(s_lbl)
        t_tokens = _tokens(t_lbl)
        text = raw_text.get(c, "")
        s_hit = any(tok in text for tok in s_tokens) if s_tokens else False
        t_hit = any(tok in text for tok in t_tokens) if t_tokens else False
        if s_hit and t_hit:
            passed += 1
        elif len(failed_examples) < 5:
            failed_examples.append(f"{c}: {s_lbl} -X-> {t_lbl}")
    return passed, len(sampled), failed_examples


def concept_accuracy(vault: Path, cats: list, sample_n: int = 14) -> tuple[int, int]:
    """Sample concept pages, check summary tokens appear in cited source files."""
    rng = random.Random(43)
    pages = []
    for c in cats:
        for f in (vault / c / "concepts").glob("*.md"):
            if f.name != "_index.md":
                pages.append((c, f))
    rng.shuffle(pages)
    pages = pages[:sample_n]

    passed = 0
    for c, p in pages:
        text = p.read_text()
        fm = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        source_files = []
        if fm:
            m = re.search(r"sources:\s*\[(.*?)\]", fm.group(1))
            if m:
                source_files = [s.strip().strip('"').strip("'") for s in m.group(1).split(",") if s.strip()]
        # extract summary section tokens
        sum_match = re.search(r"## Summary\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
        summary = sum_match.group(1) if sum_match else ""
        keywords = [w for w in re.findall(r"[A-Za-z가-힣]{4,}", summary) if w.lower() not in {
            "this", "that", "with", "from", "into", "node", "based", "across", "summary"
        }][:5]
        if not keywords or not source_files:
            continue
        raw_text = " ".join(f.read_text() for f in (vault / c / "raw").glob("*.md"))
        hits = sum(1 for kw in keywords if kw.lower() in raw_text.lower())
        if hits >= len(keywords) // 2:
            passed += 1
    return passed, len(pages) if pages else 1


def adr_fidelity(vault: Path, cats: list) -> tuple[int, int]:
    """ADR content keywords appear in source notebook fulltext."""
    total = 0
    passed = 0
    for c in cats:
        for f in (vault / c / "decisions").glob("adr-*.md"):
            total += 1
            text = f.read_text()
            # extract Context section
            ctx_match = re.search(r"## Context\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
            if not ctx_match:
                continue
            kw = [w for w in re.findall(r"[A-Za-z가-힣]{4,}", ctx_match.group(1))][:5]
            raw = " ".join(rf.read_text() for rf in (vault / c / "raw").glob("*.md"))
            if sum(1 for k in kw if k.lower() in raw.lower()) >= max(1, len(kw) // 2):
                passed += 1
    return passed, total or 1


def community_label_fit(vault: Path, cats: list) -> tuple[int, int]:
    """Community label tokens appear in member node labels."""
    passed = 0
    total = 0
    for c in cats:
        gpath = vault / c / "raw" / "graphify-out" / "graph.json"
        lpath = vault / c / "raw" / "graphify-out" / ".graphify_labels.json"
        if not (gpath.exists() and lpath.exists()):
            continue
        g = json.loads(gpath.read_text())
        labels = json.loads(lpath.read_text())
        community_members = {}
        for n in g["nodes"]:
            cid = n.get("community")
            if cid is not None:
                community_members.setdefault(int(cid), []).append(n["label"])
        for cid, lbl in labels.items():
            total += 1
            members = community_members.get(int(cid), [])
            label_tokens = [t.lower() for t in re.split(r"[\s\-/·]+", lbl) if len(t) > 2]
            member_text = " ".join(members).lower()
            hits = sum(1 for t in label_tokens if t in member_text)
            if hits >= max(1, len(label_tokens) // 2):
                passed += 1
    return passed, total or 1


def cross_vault_relevance(vault: Path) -> tuple[int, int]:
    """meta/cross-vault-links real-marked targets share topic with notebook."""
    cv = vault / "meta" / "cross-vault-links.md"
    if not cv.exists():
        return 0, 1
    text = cv.read_text()
    # parse rows tagged "real"
    rows = re.findall(r"\|.*?\|.*?\|.*?\[\[(\.\./\.\./[^\]|]+)\]\].*?\|\s*real\b", text)
    if not rows:
        return 0, 1
    passed = 0
    sample = rows[:15]
    for rel in sample:
        target = (cv.parent / rel).resolve()
        actual = target.with_suffix(".md") if not target.suffix else target
        if actual.exists():
            passed += 1
    return passed, len(sample)


def hot_cache_citation(vault: Path, cats: list) -> tuple[int, int]:
    """hot.md god_nodes match actual god_nodes from analysis.json."""
    passed = 0
    total = len(cats)
    for c in cats:
        hot = vault / c / "hot.md"
        analysis = vault / c / "raw" / "graphify-out" / ".graphify_analysis.json"
        if not (hot.exists() and analysis.exists()):
            continue
        gods = json.loads(analysis.read_text()).get("gods", [])
        god_labels = {g.get("label", "") for g in gods[:5]}
        hot_text = hot.read_text()
        cited = sum(1 for g in god_labels if g in hot_text)
        if cited >= 3:
            passed += 1
    return passed, total


def hallucination_check(vault: Path, cats: list) -> tuple[int, int]:
    """Worker-generated concept/entity pages: every claim section should have wikilink to source."""
    flagged = 0
    total = 0
    for c in cats:
        for folder in ("concepts", "entities"):
            for f in (vault / c / folder).glob("*.md"):
                if f.name == "_index.md":
                    continue
                total += 1
                text = f.read_text()
                has_source = "[[../sources/" in text or "[[../raw/" in text or "source_file" in text
                if not has_source:
                    flagged += 1
    if total == 0:
        # No concept/entity pages to evaluate — return 0% grounded so empty
        # vaults don't earn the full 10pt non_hallucinated dim by default.
        return 0, 100
    pct_grounded = 1 - flagged / total
    return int(pct_grounded * 100), 100  # as percentage


def score_vault(vault: Path) -> dict:
    cats = sorted([d.name for d in vault.iterdir()
                   if d.is_dir() and (d / "raw").exists() and not d.name.startswith(".")])

    scores = {}
    details = {}

    # 1. Edge fact (30)
    passed, total, failures = edge_token_check(vault, cats, sample_n=30)
    scores["edge_fact"] = round(30 * passed / max(total, 1), 1)
    details["edge_fact"] = f"{passed}/{total} edges grounded in raw co-occurrence"
    if failures:
        details["edge_fact"] += f" (e.g. {failures[0]})"

    # 2. Concept accuracy (20)
    passed, total = concept_accuracy(vault, cats, sample_n=14)
    scores["concept_accuracy"] = round(20 * passed / max(total, 1), 1)
    details["concept_accuracy"] = f"{passed}/{total} concepts grounded"

    # 3. ADR fidelity (15)
    passed, total = adr_fidelity(vault, cats)
    scores["adr_fidelity"] = round(15 * passed / max(total, 1), 1)
    details["adr_fidelity"] = f"{passed}/{total} ADRs grounded"

    # 4. Community label fit (10)
    passed, total = community_label_fit(vault, cats)
    scores["label_fit"] = round(10 * passed / max(total, 1), 1)
    details["label_fit"] = f"{passed}/{total} labels fit members"

    # 5. Cross-vault relevance (10)
    passed, total = cross_vault_relevance(vault)
    scores["cross_vault_relevance"] = round(10 * passed / max(total, 1), 1)
    details["cross_vault_relevance"] = f"{passed}/{total} real cross-vault targets exist"

    # 6. Hot cache citation (5)
    passed, total = hot_cache_citation(vault, cats)
    scores["hot_citation"] = round(5 * passed / max(total, 1), 1)
    details["hot_citation"] = f"{passed}/{total} hot.md cites real god nodes"

    # 7. Hallucination (10) — % of concept/entity pages with source linkage
    grounded_pct, _ = hallucination_check(vault, cats)
    scores["non_hallucinated"] = round(10 * grounded_pct / 100, 1)
    details["non_hallucinated"] = f"{grounded_pct}% pages have source linkage"

    total = min(100, sum(scores.values()))
    return {
        "total": round(total, 1),
        "scores": scores,
        "details": details,
        "categories": cats,
        "type": "content",
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: score_content.py <vault-path>", file=sys.stderr)
        sys.exit(1)
    vault = Path(sys.argv[1]).expanduser().resolve()
    if not vault.exists():
        print(f"Vault not found: {vault}", file=sys.stderr)
        sys.exit(1)

    state = score_vault(vault)

    print("=" * 60)
    print(f"Content Accuracy Score: {state['total']:.1f}/100")
    print("=" * 60)
    max_pts = _load_max_pts()
    for k, v in state["scores"].items():
        print(f"  {k:25} {v:5.1f}/{max_pts.get(k, 10):2} — {state['details'][k]}")

    out = vault / "meta" / "score-content-state.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    print(f"\nSaved {out.relative_to(vault)}")


if __name__ == "__main__":
    main()
