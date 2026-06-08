#!/usr/bin/env python3
"""Rubric-driven verification.

Reads rubric.yaml acceptance rules and applies them to a docs tree.
Returns per-dim pass/fail + score breakdown.

Designed for code-docs rubric (rubrics/code-docs.yaml): 6 dims, 100pt, pass=95.
Generalizable: each dim's `acceptance:` block is a small DSL the verifier executes.

Acceptance DSL (YAML):
    hallucination:
      max: 30
      acceptance:
        per_finding_penalty: -10
        zero_findings_required: true
        verifier_method: "drift_claim_drift_count"   # named verifier function
    completeness:
      max: 20
      acceptance:
        core_files_covered_pct: 1.0
        verifier_method: "gap_zero_required"

Named verifier functions live in VERIFIERS dict below; each takes (repo, docs_root,
scan_code_result, scan_docs_result, drift_report) and returns (score: float, detail: str).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from pipeline import drift as drift_mod
    from pipeline import scan_code, scan_docs
else:
    from pipeline import drift as drift_mod
    from pipeline import scan_code, scan_docs

try:
    import yaml
except ImportError:
    yaml = None


PLUGIN_ROOT = Path(__file__).resolve().parent.parent


# ──── Named verifiers ─────────────────────────────────────────────────────────


def _v_hallucination(ctx: dict, dim_cfg: dict) -> tuple[float, str]:
    """Score 30 minus 10 per claim_drift + symbol_drift entry (floor at 0)."""
    claim = len(ctx["drift"]["claim_drift"])
    sym = len(ctx["drift"]["symbol_drift"])
    findings = claim + sym
    penalty = dim_cfg.get("per_finding_penalty", -10)
    score = max(0.0, dim_cfg.get("max", 30) + findings * penalty)
    return score, f"{findings} findings (claim={claim}, symbol={sym}), score {score}"


def _v_completeness(ctx: dict, dim_cfg: dict) -> tuple[float, str]:
    """Score scales linearly with covered_pct = 1 - gap / total_public_modules."""
    gap = len(ctx["drift"]["gap"])
    total = sum(1 for m, info in ctx["code"].items()
                if info.get("public_classes") or info.get("public_functions"))
    if total == 0:
        return float(dim_cfg.get("max", 20)), "no public modules; trivially complete"
    covered_pct = max(0.0, 1.0 - gap / total)
    target = dim_cfg.get("core_files_covered_pct", 1.0)
    score = round(dim_cfg.get("max", 20) * (covered_pct / target if target else 1), 1)
    score = min(score, dim_cfg.get("max", 20))
    return score, f"{total - gap}/{total} covered ({covered_pct:.0%})"


def _v_cross_link(ctx: dict, dim_cfg: dict) -> tuple[float, str]:
    """Score by % docs that have ≥N wikilinks."""
    n_min = int(dim_cfg.get("wikilinks_per_page_min", 3))
    docs = ctx["docs"]
    if not docs:
        return 0.0, "no docs"
    passed = sum(1 for info in docs.values() if len(info.get("wikilinks", [])) >= n_min)
    score = round(dim_cfg.get("max", 15) * passed / len(docs), 1)
    return score, f"{passed}/{len(docs)} docs have ≥{n_min} wikilinks"


def _v_examples(ctx: dict, dim_cfg: dict) -> tuple[float, str]:
    """Total file:line citations across all docs vs threshold."""
    min_total = int(dim_cfg.get("file_line_citations_min", 10))
    total = sum(
        sum(1 for ref in info.get("code_refs", []) if ":" in ref)
        for info in ctx["docs"].values()
    )
    score = min(dim_cfg.get("max", 15), round(dim_cfg.get("max", 15) * total / max(min_total, 1), 1))
    return score, f"{total} file:line citations (target ≥{min_total})"


def _v_structure(ctx: dict, dim_cfg: dict) -> tuple[float, str]:
    """% docs with required frontmatter fields."""
    required = dim_cfg.get("frontmatter_required") or []
    docs = ctx["docs"]
    if not docs:
        return 0.0, "no docs"
    if not required:
        return float(dim_cfg.get("max", 10)), "no required fields configured"
    passed = sum(1 for info in docs.values()
                 if all(k in (info.get("frontmatter") or {}) for k in required))
    score = round(dim_cfg.get("max", 10) * passed / len(docs), 1)
    return score, f"{passed}/{len(docs)} docs have all required fm fields: {required}"


def _v_accuracy(ctx: dict, dim_cfg: dict) -> tuple[float, str]:
    """Inverse of claim_drift ratio over total signatures referenced."""
    claim = len(ctx["drift"]["claim_drift"])
    # rough denominator = signatures across code
    total_sigs = sum(len(info.get("signatures", {})) for info in ctx["code"].values())
    if total_sigs == 0:
        return float(dim_cfg.get("max", 20)), "no signatures to check"
    accuracy = max(0.0, 1.0 - claim / total_sigs)
    score = round(dim_cfg.get("max", 20) * accuracy, 1)
    return score, f"{total_sigs - claim}/{total_sigs} sigs accurate ({accuracy:.1%})"


VERIFIERS: dict[str, Callable[[dict, dict], tuple[float, str]]] = {
    "hallucination": _v_hallucination,
    "completeness": _v_completeness,
    "cross_link": _v_cross_link,
    "examples": _v_examples,
    "structure": _v_structure,
    "accuracy": _v_accuracy,
}


# ──── Driver ──────────────────────────────────────────────────────────────────


def verify(repo: Path, doc_root: Path | None = None, rubric_path: Path | None = None) -> dict:
    """Provide the public verify API."""
    repo = repo.expanduser().resolve()
    doc_root = (doc_root or repo).expanduser().resolve()
    rubric_path = rubric_path or (PLUGIN_ROOT / "rubrics" / "code-docs.yaml")
    if yaml is None:
        raise RuntimeError("pyyaml required for verify.py")
    rubric = yaml.safe_load(rubric_path.read_text())

    ctx = {
        "code": scan_code.scan_tree(repo),
        "docs": scan_docs.scan_tree(doc_root),
        "drift": drift_mod.detect(repo, doc_root).to_dict(),
    }

    results = {"rubric": str(rubric_path), "repo": str(repo), "dimensions": {}, "total": 0.0, "max": 0, "pass": False}
    pass_threshold = rubric.get("structural", {}).get("pass_threshold", 95)

    for dim_name, dim_cfg in (rubric.get("structural", {}).get("dimensions") or {}).items():
        verifier = VERIFIERS.get(dim_name)
        if not verifier:
            results["dimensions"][dim_name] = {
                "score": 0.0, "max": dim_cfg.get("max", 10),
                "detail": "no verifier registered — skipped (treated as zero)",
            }
            results["max"] += dim_cfg.get("max", 10)
            continue
        score, detail = verifier(ctx, {**dim_cfg.get("acceptance", {}), "max": dim_cfg.get("max", 10)})
        results["dimensions"][dim_name] = {"score": score, "max": dim_cfg.get("max", 10), "detail": detail}
        results["total"] += score
        results["max"] += dim_cfg.get("max", 10)

    results["total"] = round(results["total"], 1)
    results["pass"] = results["total"] >= pass_threshold
    results["pass_threshold"] = pass_threshold
    return results


def main(argv: list[str]) -> int:
    """Run the verify command-line entry point."""
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path)
    ap.add_argument("--doc-root", type=Path, default=None)
    ap.add_argument("--rubric", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--format", choices=["json", "md"], default="md")
    args = ap.parse_args(argv[1:])

    results = verify(args.repo, args.doc_root, args.rubric)
    if args.format == "json":
        content = json.dumps(results, indent=2, ensure_ascii=False)
    else:
        lines = [f"# Verify Report — {results['repo']}", "",
                 f"**Score: {results['total']}/{results['max']}** "
                 f"(pass ≥ {results['pass_threshold']}: {'✅' if results['pass'] else '❌'})",
                 "",
                 "| Dim | Score | Max | Detail |", "|---|---|---|---|"]
        for k, v in results["dimensions"].items():
            lines.append(f"| {k} | {v['score']} | {v['max']} | {v['detail']} |")
        content = "\n".join(lines)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(content)
        sys.stdout.write(f"wrote {args.out}\n")
    else:
        sys.stdout.write(content + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
