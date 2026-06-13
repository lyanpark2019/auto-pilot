"""Exit-gate evidence validation for auto-pilot review rounds.

A review round may only count toward a successful phase when it carries a
complete evidence chain: claude-reviewer APPROVE plus codex-reviewer APPROVE
or honest ABSTAIN (bounded-timeout with a non-empty abstain_reason). This is
the load-bearing catch for the run-3 bypass (phase advanced with a missing
reviewer ticket and an empty reviewer output dir, yet state.json recorded
APPROVE).

Chain checks (in order):
1. frozen.diff + .sha256 present and sha matches recomputed value.
2. contract.json present and PM-SIGNATURE validates the context/contract shas.
3. contract.json readable.
4. Per role: ticket present and ticket.diff_sha256 == actual sha.
5. Per role: review.json present and schema-valid.
6. Per role: review.json reviewer field == role dir name (copy-across-roles guard).
7. Verdict check: claude-reviewer APPROVE; codex-reviewer APPROVE or honest
   ABSTAIN (non-empty abstain_reason). APPROVE requires scope_check=PASS —
   scope_check=FAIL (contradictory evidence) and scope_check=SKIPPED (abstain-
   only field) both block.
8. Per role: contract_id matches contract.json id.

Principle: evidence over trust — the gate recomputes the diff SHA and refuses
trust in any artifact it cannot verify. A MISSING/empty review.json is never
an implicit abstain — run-3 hardening is the reason this gate exists.
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


def _verdict_failure(role: str, data: dict[str, Any]) -> str | None:
    """None when the verdict is acceptable for this role, else failure text.

    codex-reviewer may ABSTAIN (honest bounded-timeout: verdict ABSTAIN plus a
    non-empty reviewer_meta.abstain_reason) — codex unavailability (honest
    ABSTAIN) never blocks; a codex REJECT still does. claude-reviewer is the
    load-bearing verdict: APPROVE only. A MISSING/empty review.json stays
    blocked in the caller regardless (run-3 hardening — an absent file is
    never an implicit abstain).

    APPROVE is acceptable only with scope_check=PASS. scope_check=FAIL means
    the reviewer flagged an out-of-scope diff and approving it is contradictory
    evidence — blocked. scope_check=SKIPPED is only valid on ABSTAIN. APPROVE
    also requires verify_rerun.exit_code==0 — the reviewer's own re-run failing
    while it approves is contradictory evidence (codex honest ABSTAIN, which
    carries the timeout/exec exit code, is exempt because it is not APPROVE).
    """
    verdict = data.get("verdict")
    if verdict == "APPROVE":
        sc = data.get("scope_check")
        if sc == "SKIPPED":
            return f"{role}: scope_check=SKIPPED only valid with verdict=ABSTAIN"
        if sc == "FAIL":
            return (f"{role}: scope_check=FAIL — an out-of-scope diff cannot be "
                    f"approved evidence (contradictory)")
        rerun = data.get("verify_rerun")
        exit_code = rerun.get("exit_code") if isinstance(rerun, dict) else None
        if not isinstance(exit_code, int) or exit_code != 0:
            return (f"{role}: APPROVE with verify_rerun.exit_code={exit_code!r} "
                    f"(need 0 — contradictory evidence)")
        return None
    if role == "codex-reviewer" and verdict == "ABSTAIN":
        meta = data.get("reviewer_meta")
        reason = str(meta.get("abstain_reason") or "") if isinstance(meta, dict) else ""
        if reason.strip():
            return None
        return f"{role}: verdict=ABSTAIN without reviewer_meta.abstain_reason"
    return f"{role}: verdict={verdict!r} (need APPROVE)"


def assert_round_evidence(contract_dir: Path) -> None:
    """Raise EvidenceError unless contract_dir holds a complete evidence chain.

    Chain: frozen.diff sha matches its recorded .sha256; PM-SIGNATURE binds
    the context-bundle manifest and contract bytes; both reviewer tickets bind
    that sha; both review.json are schema-valid; review.json reviewer field
    matches the role dir name (copy-across-roles guard); claude-reviewer APPROVE
    (with scope_check=PASS) and codex-reviewer APPROVE or honest ABSTAIN
    (non-empty abstain_reason); both carry the round's contract id.
    """
    failures: list[str] = []

    frozen = contract_dir / "review-input" / "frozen.diff"
    sha_file = contract_dir / "review-input" / "frozen.diff.sha256"
    contract_file = contract_dir / "contract.json"

    if not frozen.exists() or not sha_file.exists():
        raise EvidenceError(f"{contract_dir}: missing frozen.diff or frozen.diff.sha256")
    if not contract_file.exists():
        raise EvidenceError(f"{contract_dir}: missing contract.json")
    try:
        _contract.verify_pm_signature(contract_dir)
    except (OSError, json.JSONDecodeError, KeyError, TypeError,
            _contract.PMSignatureMismatchError) as exc:
        failures.append(f"PM-SIGNATURE invalid: {exc}")

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
        reviewer_value = str(data.get("reviewer") or "")
        if reviewer_value != role:
            failures.append(
                f"{role}: review.json reviewer field {reviewer_value!r} != role dir "
                f"(review copied across roles?)"
            )
        verdict_failure = _verdict_failure(role, data)
        if verdict_failure is not None:
            failures.append(verdict_failure)
        if str(data.get("contract_id") or "") != contract_id:
            failures.append(f"{role}: contract_id {data.get('contract_id')!r} != {contract_id!r}")

    if failures:
        raise EvidenceError(f"{contract_dir}: " + "; ".join(failures))


def gate_phase_end(contracts_root: Path) -> tuple[str, str] | int:
    """Evidence gate for a successful phase-end.

    Returns the approved-contract count (int ≥ 0) when every active-phase round
    dir holds a complete evidence chain. Otherwise returns
    (event_suffix, blocked_message): event_suffix is "no_evidence_dirs" or
    "evidence_failed" for the caller's structured log.
    """
    round_dirs = latest_round_dirs_for_active_phase(contracts_root)
    if not round_dirs:
        return ("no_evidence_dirs",
                f"BLOCKED phase-end --status success: no contract round dirs under {contracts_root}")
    approved = 0
    for round_dir in round_dirs:
        try:
            assert_round_evidence(round_dir)
            approved += 1
        except EvidenceError as exc:
            return ("evidence_failed", f"BLOCKED phase-end --status success: {exc}")
    return approved


def _phase_num(phase_dir: Path) -> int:
    try:
        return int(phase_dir.name.split("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def _iter_num(iter_dir: Path) -> int:
    try:
        return int(iter_dir.name.split("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def _round_num(round_dir: Path) -> int:
    try:
        return int(round_dir.name.split("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def latest_round_dirs_for_active_phase(contracts_root: Path) -> list[Path]:
    """Latest round-* dir of each contract under the CURRENT iteration's max phase.

    Scopes to the max iter-N dir (the current iteration — iter numbers increment
    monotonically per outer-loop pass), THEN the max phase-N within it. A global
    max phase across iterations would validate a stale earlier iteration's
    evidence while the current iteration's phase is evidence-free (the exact
    bypass this gate exists to close). Returns [] when no iter-*/phase-* tree
    exists; the caller treats [] as BLOCKED (fail-closed). Requires the
    iter-N/phase-M/contract-K/round-R layout — a flat phase-* layout (no iter-*
    parent) returns [] and is therefore blocked (documented residual; the live
    loop always uses the iter-N layout).
    """
    if not contracts_root.exists():
        return []
    iter_dirs = [d for d in contracts_root.glob("iter-*") if d.is_dir()]
    if not iter_dirs:
        return []
    current_iter = max(iter_dirs, key=_iter_num)
    phase_dirs = [p for p in current_iter.glob("phase-*") if p.is_dir()]
    if not phase_dirs:
        return []
    max_phase = max(_phase_num(p) for p in phase_dirs)
    out: list[Path] = []
    for phase_dir in phase_dirs:
        if _phase_num(phase_dir) != max_phase:
            continue
        for contract_dir in sorted(phase_dir.glob("contract-*")):
            rounds = sorted(contract_dir.glob("round-*"), key=_round_num)
            if rounds:
                out.append(rounds[-1])
    return out
