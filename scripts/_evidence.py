"""Exit-gate evidence validation for auto-pilot review rounds.

A review round may only count toward a successful phase when it carries a
complete, sha-bound, dual-APPROVE evidence chain. This is the load-bearing
catch for the run-3 bypass (phase advanced with a missing reviewer ticket and
an empty reviewer output dir, yet state.json recorded APPROVE).

Principle: evidence over trust — the gate recomputes the diff SHA and refuses
trust in any artifact it cannot verify.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import _contract
import _dispatch

REVIEWERS = ("codex-reviewer", "claude-reviewer")


class EvidenceError(Exception):
    """Raised when a review round's evidence chain is incomplete or inconsistent."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise EvidenceError(f"{path}: unreadable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceError(f"{path}: expected JSON object, got {type(data).__name__}")
    return data


def assert_round_evidence(contract_dir: Path) -> None:
    """Raise EvidenceError unless contract_dir holds a complete dual-APPROVE chain.

    Chain: frozen.diff sha matches its recorded .sha256; both reviewer tickets
    bind that sha; both review.json are schema-valid, APPROVE, and carry the
    round's contract id.
    """
    failures: list[str] = []

    frozen = contract_dir / "review-input" / "frozen.diff"
    sha_file = contract_dir / "review-input" / "frozen.diff.sha256"
    contract_file = contract_dir / "contract.json"

    if not frozen.exists() or not sha_file.exists():
        raise EvidenceError(f"{contract_dir}: missing frozen.diff or frozen.diff.sha256")
    if not contract_file.exists():
        raise EvidenceError(f"{contract_dir}: missing contract.json")

    recorded_sha = sha_file.read_text().strip()
    actual_sha = _contract._sha256(frozen.read_bytes())
    if recorded_sha != actual_sha:
        failures.append(f"frozen.diff sha mismatch (recorded={recorded_sha}, actual={actual_sha})")

    contract_id = str(_read_json(contract_file).get("id") or "")

    for role in REVIEWERS:
        ticket = contract_dir / "tickets" / f"{role}.json"
        review = contract_dir / "outputs" / role / "review.json"
        if not ticket.exists():
            failures.append(f"{role}: ticket missing")
        else:
            ticket_sha = str(_read_json(ticket).get("diff_sha256") or "")
            if ticket_sha != actual_sha:
                failures.append(f"{role}: ticket diff_sha256 != frozen.diff sha")
        if not review.exists():
            failures.append(f"{role}: review.json missing")
            continue
        try:
            data = _dispatch.read_review(review)
        except (_dispatch.MalformedReviewError, json.JSONDecodeError) as exc:
            failures.append(f"{role}: review.json unreadable/invalid: {exc}")
            continue
        if data.get("verdict") != "APPROVE":
            failures.append(f"{role}: verdict={data.get('verdict')!r} (need APPROVE)")
        if str(data.get("contract_id") or "") != contract_id:
            failures.append(f"{role}: contract_id {data.get('contract_id')!r} != {contract_id!r}")

    if failures:
        raise EvidenceError(f"{contract_dir}: " + "; ".join(failures))


def gate_phase_end(contracts_root: Path) -> tuple[str, str] | None:
    """Evidence gate for a successful phase-end.

    Returns None when every active-phase round dir holds a complete evidence
    chain. Otherwise returns (event_suffix, blocked_message): event_suffix is
    "no_evidence_dirs" or "evidence_failed" for the caller's structured log.
    """
    round_dirs = latest_round_dirs_for_active_phase(contracts_root)
    if not round_dirs:
        return ("no_evidence_dirs",
                f"BLOCKED phase-end --status success: no contract round dirs under {contracts_root}")
    for round_dir in round_dirs:
        try:
            assert_round_evidence(round_dir)
        except EvidenceError as exc:
            return ("evidence_failed", f"BLOCKED phase-end --status success: {exc}")
    return None


def _phase_num(phase_dir: Path) -> int:
    try:
        return int(phase_dir.name.split("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def latest_round_dirs_for_active_phase(contracts_root: Path) -> list[Path]:
    """Return the latest round-* dir of each contract under the highest phase-N.

    Sequential phase execution means the max phase dir present is the one being
    closed. Returns [] when no contracts tree exists.
    """
    if not contracts_root.exists():
        return []
    phase_dirs: list[Path] = []
    for iter_dir in sorted(contracts_root.glob("iter-*")):
        phase_dirs.extend(p for p in iter_dir.glob("phase-*") if p.is_dir())
    if not phase_dirs:
        return []
    max_phase = max(_phase_num(p) for p in phase_dirs)
    out: list[Path] = []
    for phase_dir in phase_dirs:
        if _phase_num(phase_dir) != max_phase:
            continue
        for contract_dir in sorted(phase_dir.glob("contract-*")):
            rounds = sorted(contract_dir.glob("round-*"), key=lambda d: d.name)
            if rounds:
                out.append(rounds[-1])
    return out
