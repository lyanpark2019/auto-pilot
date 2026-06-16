"""Deterministic producer: convert reviewer REJECT findings → critic-rejections JSONL.

WHY this exists: The Hermes learning miner scans
``.planning/auto-pilot/critic-rejections-phase-N.jsonl`` to accumulate
improvement tickets from past reviewer rejections.  Before this module, those
JSONL files were only written by agent prose (tech-critic-lead, retro) — so the
rich findings emitted by the dual adversarial reviewers (codex-reviewer,
claude-reviewer) into ``review.json`` *never* reached learning organically.

This module is the symmetric CODE-SIDE complement to ``_resolve_learnings_cli``
(injection out) — it implements CAPTURE in.

Design constraints (enforce-with-code, not prompts):
  - Pure Python, no LLM, no subprocess, advisory-only (never raises to callers).
  - File-level idempotent when ``dedupe=True``: the dedupe KEY is
    ``json.dumps(line, sort_keys=True)``; cross-reviewer duplicates within one
    capture call are collapsed by the same set.
  - Only P0/P1 findings from REJECT reviews are written (P2 is cosmetic noise).
  - ``candidate_asset`` is always ``None`` — a deterministic producer must not
    infer asset type from free text.
  - ``line`` and ``fix`` are dropped from the JSONL line — the miner never reads
    ``line``; ``fix`` destabilises the fingerprint.
  - Absolute or repo-prefixed file paths are normalised to repo-relative so
    ``_learnings._scope_match`` (exact-path / ``scope/``-prefix) works correctly.
  - The canonical dedupe key includes ``run_id``, so the same finding captured
    under a different ``run_id`` is a genuinely new JSONL line.  This lets the
    miner count distinct runs and detect recurrence.  A re-capture within the
    same run is deduped by the identical ``(file, issue, run_id)`` key.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import learning_miner as _learning_miner


# ---------------------------------------------------------------------------
# Path normalisation
# ---------------------------------------------------------------------------

def _repo_relative(file_str: str, repo_root: Path) -> str:
    """Return repo-relative form of ``file_str``, stripping leading ``./``.

    Absolute paths are made relative via ``Path.relative_to(repo_root)``.
    If the path is not under repo_root (ValueError), the raw string is
    returned unchanged — an out-of-repo path simply won't scope-match,
    rather than producing a misleading ``../../`` traversal.
    Relative paths have a leading ``./`` stripped for predictable scope-match.
    """
    if not file_str:
        return file_str
    p = Path(file_str)
    if p.is_absolute():
        try:
            return str(p.relative_to(repo_root))
        except ValueError:
            return file_str
    # Relative path: strip a leading "./" so scope-match works predictably.
    raw = str(p)
    if raw.startswith("./"):
        raw = raw[2:]
    return raw


def _provenance_run_id(review_path: Path, fallback: str) -> str:
    """Return the run_id that PRODUCED this review, read from its PM-SIGNATURE.

    A review at ``<contract_dir>/outputs/<role>/review.json`` is signed at
    ``<contract_dir>/PM-SIGNATURE`` (``_contract.write_pm_signature``) with the
    dispatching run's run_id.  Stamping captured lines with THAT run_id — not the
    scan-time state run_id — makes a re-scan of a persisted ``review.json``
    idempotent: the same physical finding always carries the same run_id, so a
    later session re-scanning an earlier run's persisted reviews cannot inflate
    ``distinct_runs``.  Missing/unreadable/empty signature → ``fallback``.
    """
    try:
        contract_dir = review_path.parents[2]
    except IndexError:
        return fallback
    try:
        sig = json.loads((contract_dir / "PM-SIGNATURE").read_text())
    except (OSError, json.JSONDecodeError, ValueError):
        return fallback
    if isinstance(sig, dict):
        run_id = sig.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            return run_id
    return fallback


# ---------------------------------------------------------------------------
# Core producer
# ---------------------------------------------------------------------------

def capture_phase(repo_root: Path, phase: int, *, dedupe: bool = True) -> int:
    """Convert reviewer REJECT findings for ``phase`` into critic-rejections JSONL.

    Each written line carries the run_id of the run that PRODUCED the review
    (read from the contract's PM-SIGNATURE), falling back to the live state
    run_id when no signature is present.  Provenance stamping makes a re-scan of
    a persisted ``review.json`` idempotent, so a later session sweeping an
    earlier run's reviews cannot inflate distinct_runs.

    Returns the number of NEW lines appended.  Best-effort: a malformed or
    missing ``review.json`` is skipped, never raised.  Idempotent at the file
    level when ``dedupe=True``.
    """
    import _dispatch  # noqa: PLC0415 — local import keeps the module importable without the full env

    fallback_run_id: str = _learning_miner.current_run_id(repo_root)

    planning = repo_root / ".planning" / "auto-pilot"
    jsonl_path = planning / f"critic-rejections-phase-{phase}.jsonl"

    # Build a glob that matches phase-{phase} exactly (as a full path segment).
    contracts_base = planning / "contracts"
    pattern = f"iter-*/phase-{phase}/contract-*/round-*/outputs/*/review.json"
    review_files = sorted(contracts_base.glob(pattern))

    # --- Build the canonical-key set from existing JSONL lines (dedupe). ---
    existing_keys: set[str] = set()
    if dedupe and jsonl_path.exists():
        try:
            for raw in jsonl_path.read_text().splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                    existing_keys.add(json.dumps(obj, sort_keys=True))
                except json.JSONDecodeError:
                    pass
        except OSError:
            pass

    # Keys for lines we will write in this call (cross-reviewer dedupe).
    new_keys: set[str] = set()
    new_lines: list[str] = []

    for review_path in review_files:
        try:
            review = _dispatch.read_review(review_path)
        except (_dispatch.MalformedReviewError, OSError, json.JSONDecodeError, ValueError):
            continue

        if review.get("verdict") != "REJECT":
            continue

        line_run_id = _provenance_run_id(review_path, fallback_run_id)

        raw_findings = review.get("findings", [])
        findings: list[Any] = list(raw_findings) if isinstance(raw_findings, list) else []
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            if finding.get("severity") not in {"P0", "P1"}:
                continue

            file_str = finding.get("file", "")
            if not isinstance(file_str, str):
                file_str = str(file_str)
            file_str = _repo_relative(file_str, repo_root)

            issue_str = finding.get("issue", "")
            if not isinstance(issue_str, str):
                issue_str = str(issue_str)

            line: dict[str, Any] = {
                "file": file_str,
                "issue": issue_str,
                "candidate_asset": None,
                "run_id": line_run_id,
            }
            canon_key = json.dumps(line, sort_keys=True)
            if dedupe and (canon_key in existing_keys or canon_key in new_keys):
                continue
            new_keys.add(canon_key)
            new_lines.append(json.dumps(line))

    if not new_lines:
        return 0

    # Ensure parent directory exists, then append.
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a") as fh:
        for text in new_lines:
            fh.write(text + "\n")

    return len(new_lines)


def _discover_phases(repo_root: Path) -> list[int]:
    """Distinct phase numbers present under the contracts tree, sorted."""
    contracts_base = repo_root / ".planning" / "auto-pilot" / "contracts"
    phases: set[int] = set()
    for phase_dir in contracts_base.glob("iter-*/phase-*"):
        name = phase_dir.name
        if phase_dir.is_dir() and name.startswith("phase-"):
            try:
                phases.add(int(name[len("phase-"):]))
            except ValueError:
                continue
    return sorted(phases)


def capture_all_phases(repo_root: Path, *, dedupe: bool = True) -> int:
    """Sweep every phase under the contracts tree through ``capture_phase``.

    Driven by the Stop-hook chokepoint (``hooks/learning-miner-stop.sh``) so
    capture runs deterministically at session end across ALL phases — including
    phases that pivot-aborted before a clean phase-end (their ``review.json``
    persist on disk).  Best-effort: a per-phase failure is swallowed so one bad
    phase never blocks the rest.  Returns total NEW lines appended.
    """
    total = 0
    for phase in _discover_phases(repo_root):
        try:
            total += capture_phase(repo_root, phase, dedupe=dedupe)
        except Exception:  # advisory sweep — one bad phase must not block the rest
            continue
    return total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def register_cli_subparsers(sub: Any) -> None:
    """Register ``capture-reviews`` + ``capture-all-phases`` onto the orchestrator CLI."""
    p = sub.add_parser("capture-reviews")
    p.add_argument(
        "--repo-root", default=".", dest="repo_root",
        help="project root (default: .)",
    )
    p.add_argument(
        "--phase", type=int, required=True, dest="phase",
        help="phase number to capture",
    )
    p.set_defaults(func=cmd_capture_reviews)

    pa = sub.add_parser("capture-all-phases")
    pa.add_argument(
        "--repo-root", default=".", dest="repo_root",
        help="project root (default: .)",
    )
    pa.set_defaults(func=cmd_capture_all_phases)


def cmd_capture_reviews(args: Any) -> int:
    """Capture reviewer REJECT findings into the JSONL for the given phase.

    Always returns 0 — capture failure must never fail the loop.
    """
    repo_root = Path(args.repo_root).resolve()
    try:
        appended = capture_phase(repo_root, int(args.phase))
    except Exception as exc:  # advisory: capture failure must never fail the loop
        sys.stderr.write(f"capture-reviews: error, captured nothing: {exc}\n")
        sys.stdout.write(
            json.dumps({"ok": False, "phase": int(args.phase), "appended": 0,
                        "jsonl_path": None}) + "\n"
        )
        return 0
    jsonl_path = (
        repo_root / ".planning" / "auto-pilot"
        / f"critic-rejections-phase-{int(args.phase)}.jsonl"
    )
    sys.stdout.write(
        json.dumps({"ok": True, "phase": int(args.phase), "appended": appended,
                    "jsonl_path": str(jsonl_path)}) + "\n"
    )
    return 0


def cmd_capture_all_phases(args: Any) -> int:
    """Sweep every phase's reviewer REJECT findings into JSONL. Always returns 0."""
    repo_root = Path(args.repo_root).resolve()
    try:
        appended = capture_all_phases(repo_root)
    except Exception as exc:  # advisory: capture failure must never fail the loop
        sys.stderr.write(f"capture-all-phases: error, captured nothing: {exc}\n")
        sys.stdout.write(json.dumps({"ok": False, "appended": 0}) + "\n")
        return 0
    sys.stdout.write(json.dumps({"ok": True, "appended": appended}) + "\n")
    return 0
