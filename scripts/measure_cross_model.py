"""measure_cross_model.py — cross-MODEL class-convergence measurement (R1's last open unknown).

The R1 fix keys a reviewer-finding fingerprint on a controlled-vocab ``class`` so
the SAME defect phrased differently collapses to ONE ticket and ``distinct_runs``
reaches the promotion gate. Its load-bearing, UNPROVEN assumption: the codex
reviewer AND the claude reviewer independently pick the SAME ``class`` token for
one defect. If they disagree the fingerprint fragments at the class level and the
defect never accumulates cross-model recurrence.

This instrument runs the REAL miner over collected ``review.json`` outputs — no R1
logic is reimplemented here. ``scan_reviewer_findings`` derives the exact keyed
issue (class-when-valid-else-prose, with the strip/lower normalize + empty skip),
``bump_or_create`` accumulates ``distinct_runs`` exactly as the loop does, and
``is_promotable`` applies the real reviewer-finding threshold. Each ``(model, pass)``
is stamped as a distinct ``run_id`` (simulating cross-run recurrence); a fingerprint
whose evidence run_ids span BOTH models is the money case — one ticket reached by
codex and claude, the only way the gate fires from a cross-model pair.

CLI (via orchestrator.py):
    orchestrator.py measure-cross-model --runs <dir> --defects <defects.json> [--json]
"""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _improvement as imp
import learning_miner as lm
from _dispatch import MalformedReviewError, read_review

# Reviewer dir names the producer writes under <runs>/<model>/pass-N/review.json.
_MODELS = ("claude-reviewer", "codex-reviewer")
_REVIEWER_THRESHOLD = lm.PROMOTION_THRESHOLDS["reviewer-finding"]
# Fixed timestamp — the output never includes it; pinning keeps bump_or_create
# deterministic without datetime.now().
_FIXED_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _norm_class(raw: Any) -> str:
    """The miner's class normalization: strip/lower, keep only in-vocab tags."""
    norm = raw.strip().lower() if isinstance(raw, str) else ""
    return norm if norm in lm.REVIEWER_FINDING_CLASSES else ""


def _basename(finding: dict[str, Any]) -> str:
    f = finding.get("file", "")
    return Path(f).name if isinstance(f, str) and f else ""


def _defect_for_basename(base: str, defects: list[dict[str, Any]]) -> str | None:
    """The defect a basename belongs to. Matching is basename-only and unique:
    ``_validate_defects`` guarantees one defect per basename, so the convergence
    view (finding→defect) and the promotion view (fingerprint→defect) use this
    same single mapping — no line-window divergence, no first-defect misattribution.
    """
    for d in defects:
        if d.get("file_basename") == base:
            return str(d.get("name", base))
    return None


def _match_defect(finding: dict[str, Any], defects: list[dict[str, Any]]) -> str | None:
    """Return the defect name a finding belongs to (by file basename)."""
    return _defect_for_basename(_basename(finding), defects)


def _validate_defects(defects: list[dict[str, Any]]) -> None:
    """One defect per basename — the analyzer cannot disambiguate two defects in one
    file (the reused miner fingerprint carries no line), so a collision is a spec error."""
    seen: set[str] = set()
    for d in defects:
        base = d.get("file_basename")
        if not isinstance(base, str) or not base:
            raise ValueError(f"defect missing file_basename: {d!r}")
        if base in seen:
            raise ValueError(
                f"two defects share basename {base!r}; the analyzer matches by basename "
                "only — put each seeded defect in its own file")
        seen.add(base)


def _load_reviews(runs_dir: Path) -> list[dict[str, Any]]:
    """Read every <runs>/<model>/pass-*/review.json into review records.

    A malformed review.json is skipped (recorded as a load error, not crashed).
    Record shape: {model, pass, verdict, findings, error}.
    """
    out: list[dict[str, Any]] = []
    for model in _MODELS:
        for pass_dir in sorted((runs_dir / model).glob("pass-*")):
            rj = pass_dir / "review.json"
            if not rj.exists():
                continue
            try:
                data = read_review(rj)
            except (MalformedReviewError, OSError, json.JSONDecodeError):
                out.append({"model": model, "pass": pass_dir.name, "verdict": None,
                            "findings": [], "error": True})
                continue
            findings = data.get("findings")
            out.append({
                "model": model,
                "pass": pass_dir.name,
                "verdict": data.get("verdict"),
                "findings": findings if isinstance(findings, list) else [],
                "error": False,
            })
    return out


def measure(reviews: list[dict[str, Any]], defects: list[dict[str, Any]], *,
            work_dir: Path) -> dict[str, Any]:
    """Compute cross-model convergence over collected review records.

    Deterministic given (reviews, defects): a clean ledger is built under
    ``work_dir`` each call, the real miner accumulates distinct_runs, and the
    output dict excludes paths/timestamps so shuffled input yields byte-identical
    JSON. ``work_dir`` must be empty/disposable (one tempdir per call).
    """
    _validate_defects(defects)
    planning = work_dir / ".planning" / "auto-pilot"
    planning.mkdir(parents=True, exist_ok=True)
    ledger = imp.ledger_dir(work_dir, work_dir / "ledger")

    # Per-defect, per-model raw class multisets (human-readable convergence view)
    # and the JSONL the real scanner consumes (truth view).
    per_defect_classes: dict[str, dict[str, Counter[str]]] = {}
    jsonl_lines: list[str] = []
    abstain = Counter[str]()
    passes_per_model = Counter[str]()
    both_data: dict[str, set[str]] = {}

    for rec in reviews:
        model, pass_n = rec["model"], rec["pass"]
        passes_per_model[model] += 1
        if rec.get("verdict") == "ABSTAIN" or rec.get("error"):
            abstain[model] += 1
            continue
        run_id = f"{model}:{pass_n}"
        for finding in rec["findings"]:
            if not isinstance(finding, dict):
                continue
            defect = _match_defect(finding, defects)
            if defect is None:
                continue
            both_data.setdefault(defect, set()).add(model)
            cls = _norm_class(finding.get("class"))
            per_defect_classes.setdefault(defect, {m: Counter() for m in _MODELS})
            per_defect_classes[defect][model][cls or "<prose-fallback>"] += 1
            jsonl_lines.append(json.dumps({
                "file": finding.get("file", ""),
                "issue": finding.get("issue", ""),
                "class": finding.get("class"),
                "run_id": run_id,
            }, sort_keys=True))

    (planning / "critic-rejections-phase-0.jsonl").write_text(
        "".join(line + "\n" for line in jsonl_lines))

    # Truth view: real miner → tickets keyed by fingerprint, with evidence run_ids.
    observations = lm.scan_reviewer_findings(work_dir, "")
    tickets: dict[str, dict[str, Any]] = {}
    for obs in observations:
        t = imp.bump_or_create(ledger, obs, repo_root=work_dir, now=_FIXED_NOW, dry_run=False)
        tickets[str(t["fingerprint"])] = t

    # Map each fingerprint back to its defect (via the basename in evidence/issue),
    # then decide cross-model promotion: a single ticket whose run_ids span BOTH models.
    fp_by_defect: dict[str, list[dict[str, Any]]] = {}
    for fp, t in tickets.items():
        evidence_raw = t.get("evidence", [])
        evidence = evidence_raw if isinstance(evidence_raw, list) else []
        run_ids = {e.get("run_id", "") for e in evidence if isinstance(e, dict)}
        models = {rid.split(":", 1)[0] for rid in run_ids if isinstance(rid, str) and rid}
        dr_raw = t.get("distinct_runs", 0)
        distinct = dr_raw if isinstance(dr_raw, int) else 0
        # A fingerprint's basename is shared by all its evidence; recover the defect
        # from the observation that produced it (basename match against defects).
        base = _fp_basename(observations, fp)
        defect = _defect_for_basename(base, defects)
        if defect is None:
            continue
        fp_by_defect.setdefault(defect, []).append({
            "fingerprint": fp[:16],
            "distinct_runs": distinct,
            "models": sorted(models),
            "spans_both_models": models.issuperset(_MODELS),
            "promotable": lm.is_promotable(t),
            "cross_model_promotable": models.issuperset(_MODELS) and lm.is_promotable(t),
        })

    per_defect = _build_per_defect(defects, per_defect_classes, fp_by_defect, both_data)
    agree = [d for d in per_defect if d["cross_model_agree"]]
    # Convergence is measurable only where BOTH models produced an in-vocab class.
    measurable = [d for d in per_defect if d["both_models_classified"]]
    return {
        "abstain": dict(sorted(abstain.items())),
        "overall": {
            "cross_model_convergence_pct": (
                round(len(agree) / len(measurable) * 100, 1) if measurable else 0.0),
            "defects_cross_model_agree": len(agree),
            "defects_cross_model_promotable": sum(
                1 for d in per_defect if d["cross_model_promotable"]),
            "defects_measurable": len(measurable),
            "defects_total": len(per_defect),
        },
        "passes_per_model": dict(sorted(passes_per_model.items())),
        "per_defect": per_defect,
        "reviewer_finding_threshold": _REVIEWER_THRESHOLD,
    }


def _fp_basename(observations: list[imp.Observation], fp: str) -> str:
    for obs in observations:
        if imp.compute_fingerprint(obs.source, obs.file_basename, obs.issue,
                                   obs.candidate_asset) == fp:
            return obs.file_basename
    return ""


def _modal_class(counter: Counter[str]) -> str | None:
    """Deterministic modal class: highest count, ties broken by class name (NOT by
    insertion order — most_common ties on input order and would break byte-stability)."""
    if not counter:
        return None
    return min(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def _build_per_defect(defects: list[dict[str, Any]],
                      per_defect_classes: dict[str, dict[str, Counter[str]]],
                      fp_by_defect: dict[str, list[dict[str, Any]]],
                      both_data: dict[str, set[str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for d in defects:
        name = str(d.get("name", d.get("file_basename", "")))
        classes = per_defect_classes.get(name, {m: Counter() for m in _MODELS})
        modal = {m: _modal_class(classes[m]) for m in _MODELS}
        reported = both_data.get(name, set())
        both = reported.issuperset(_MODELS)
        # A defect is only MEASURABLE for class-convergence when BOTH models gave an
        # in-vocab class — a prose-fallback / no-class finding cannot answer "did they
        # pick the SAME class", so it must not drag the convergence rate.
        classified = {m: modal[m] not in (None, "<prose-fallback>") for m in _MODELS}
        both_classified = both and all(classified.values())
        agree = bool(both_classified
                     and modal["codex-reviewer"] == modal["claude-reviewer"])
        fps = sorted(fp_by_defect.get(name, []), key=lambda f: f["fingerprint"])
        rows.append({
            "defect": name,
            "expected_class": d.get("expected_class"),
            "file_basename": d.get("file_basename"),
            "claude_classes": dict(sorted(classes["claude-reviewer"].items())),
            "codex_classes": dict(sorted(classes["codex-reviewer"].items())),
            "claude_modal_class": modal["claude-reviewer"],
            "codex_modal_class": modal["codex-reviewer"],
            "both_models_reported": both,
            "both_models_classified": both_classified,
            "cross_model_agree": agree,
            "cross_model_promotable": any(f["cross_model_promotable"] for f in fps),
            "fingerprints": fps,
        })
    return sorted(rows, key=lambda r: r["defect"])


def _load_defects(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = data.get("defects", [])
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def register_cli_subparsers(sub: Any) -> None:
    """Register ``measure-cross-model`` onto the orchestrator CLI parser."""
    p = sub.add_parser("measure-cross-model")
    p.add_argument("--runs", required=True, help="dir with <model>/pass-N/review.json")
    p.add_argument("--defects", required=True, help="defects.json (seeded-defect spec)")
    p.add_argument("--json", action="store_true", dest="output_json",
                   help="output JSON (always true; flag kept for parity with siblings)")
    p.set_defaults(func=cmd_measure_cross_model)


def cmd_measure_cross_model(args: Any) -> int:
    """CLI handler: print JSON cross-model convergence metrics."""
    runs_dir = Path(args.runs).resolve()
    defects = _load_defects(Path(args.defects).resolve())
    reviews = _load_reviews(runs_dir)
    with tempfile.TemporaryDirectory(prefix="xmodel-") as tmp:
        result = measure(reviews, defects, work_dir=Path(tmp))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0
