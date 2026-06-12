"""Pure rebalance rule engine for the routing ledger.

Consumed by _ledger.py (re-exported) and directly by tests.
Zero IO — operates on plain dicts only.
Policy SoT: skills/auto-pilot/references/model-routing.md.

Model-token normalisation (F2): ledger records carry short agent-tool tokens
(sonnet, opus, haiku) while the ladder uses canonical YAML tokens
(sonnet-4.6-1m, opus-4.8, …). normalize_model_token() bridges the gap by
mapping rank -> ladder[rank] via _routing.model_rank so the rebalance engine
can locate any short token in the ladder without hardcoding a translation table.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import _routing

_REAL_SEVERITIES = frozenset({"P0", "P1"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_ts(ts: str) -> datetime:
    # F-E: parse ISO-8601 timestamp to an aware UTC datetime.
    # Handles Z suffix, +HH:MM offsets, fractional seconds.
    # Falls back to datetime.min (UTC) on parse failure — mis-sort risk documented.
    normalized = ts[:-1] + "+00:00" if ts.endswith("Z") else ts
    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def normalize_model_token(token: str, ladder: list[str], config: Any = None) -> str:
    """Map a short agent-tool token to its canonical ladder token.

    If the token is already present in the ladder (e.g., test ladders that use
    short tokens directly, or already-canonical tokens like "opus-4.8"), it is
    returned unchanged. Otherwise, agent_model_rank rank -> ladder[rank] is
    used to map short tokens (sonnet, opus, haiku) to canonical forms.
    Unknown tokens pass through unchanged so gpt-5.5 / session-inherit remain
    as-is (caller skips them because they are not in the ladder).
    """
    if token in ladder:
        # Already a valid ladder member — no translation needed.
        return token
    rank = _routing.model_rank(token, config)
    if rank is not None and 0 <= rank < len(ladder):
        return ladder[rank]
    return token


def _group_records(
    records: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    # Groups by (role, task_class) preserving insertion order so rule windows use arrival order.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rec in records:
        key = (str(rec.get("role") or ""), str(rec.get("task_class") or ""))
        groups.setdefault(key, []).append(rec)
    return groups


def _composite_key(role: str, task_class: str) -> str:
    # F9: composite assignment key "<role>/<task_class>" for per-task_class precision.
    return f"{role}/{task_class}"


def _current_model_for_group(
    role: str,
    task_class: str,
    assignments: dict[str, Any],
    records: list[dict[str, Any]],
) -> str | None:
    # F9: composite key first (precise), then plain role key (legacy), then record fallback.
    # Composite key — precise, set by rebalance engine.
    comp = _composite_key(role, task_class)
    if comp in assignments:
        assignment = assignments[comp]
        if isinstance(assignment, dict):
            model = assignment.get("model")
            if isinstance(model, str):
                return model
    # Plain role key — legacy/hand-authored.
    if role in assignments:
        assignment = assignments[role]
        if isinstance(assignment, dict):
            model = assignment.get("model")
            if isinstance(model, str):
                return model
    # Fallback to most recent record's model.
    for rec in reversed(records):
        m = rec.get("model")
        if isinstance(m, str):
            return m
    return None


def _ladder_step_up(model: str, ladder: list[str]) -> str | None:
    # One step higher (index-1); None at ceiling so callers skip the proposal.
    try:
        idx = ladder.index(model)
    except ValueError:
        return None
    if idx == 0:
        return None
    return ladder[idx - 1]


def _ladder_step_down(model: str, ladder: list[str]) -> str | None:
    # One step lower (index+1); None at floor so callers skip the proposal.
    try:
        idx = ladder.index(model)
    except ValueError:
        return None
    if idx >= len(ladder) - 1:
        return None
    return ladder[idx + 1]


def _latest_rebalance_for_group(
    role: str, task_class: str, rebalance_log: list[dict[str, Any]]
) -> tuple[int, dict[str, Any]] | None:
    # Returns (index, entry) so callers use index-based comparisons (F7: avoids list.index() ambiguity).
    result: tuple[int, dict[str, Any]] | None = None
    for i, e in enumerate(rebalance_log):
        if e.get("role") == role and e.get("task_class") == task_class:
            result = (i, e)
    return result


def evaluate_rebalance(
    ledger: dict[str, Any],
    ladder: list[str],
    config: Any = None,
) -> list[dict[str, Any]]:
    """Pure function: return proposed rebalance_log entries (not applied).

    Evaluates the four rules from skills/auto-pilot/references/model-routing.md:
    promote-2x-gate-fail, promote-real-p0, trial-demotion-3x-clean, revert-trial.

    Model-token normalisation (F2): short tokens (sonnet, opus, haiku) in
    assignments or records are normalised via normalize_model_token() before
    ladder lookup so they are not silently skipped.

    Groups whose current model is not in ladder after normalisation (e.g.,
    gpt-5.5, session-inherit) are silently skipped — ladder covers Claude tiers.
    Respects ladder bounds: no promote above index 0, no demote past last index.

    Re-run idempotency (F5): for each group, only records NEWER than the latest
    rebalance_log entry for that group are considered by the promote/demote rules.
    This prevents --apply re-runs from firing the same rule on the same evidence.

    Double-promote prevention (F8): at most one promote rule fires per group per
    call. Once a promote proposal is emitted, remaining promote rules are skipped.

    Args:
        ledger: validated ledger dict.
        ladder: ordered list of model tokens, best (index 0) to worst (last).
        config: optional path override forwarded to _routing helpers.

    Returns:
        List of proposed rebalance_log entries. Empty means no rules fire.
    """
    proposals: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = ledger.get("records") or []
    assignments: dict[str, Any] = ledger.get("assignments") or {}
    rebalance_log: list[dict[str, Any]] = ledger.get("rebalance_log") or []
    groups = _group_records(records)
    now = _utc_now_iso()

    for (role, task_class), group_recs in groups.items():
        raw_model = _current_model_for_group(role, task_class, assignments, group_recs)
        if raw_model is None:
            continue
        # F2: normalise short token to canonical ladder form.
        current_model = normalize_model_token(raw_model, ladder, config)
        if current_model not in ladder:
            # Unknown model (gpt-5.5, session-inherit, etc.) — skip.
            continue

        # --- F5: filter to records newer than the latest rebalance for group ---
        latest_rb = _latest_rebalance_for_group(role, task_class, rebalance_log)
        if latest_rb is not None:
            latest_rb_idx, latest_rb_entry = latest_rb
            # Records that arrived before or at the time of the last rebalance
            # entry are already "consumed" — only evaluate newer ones.
            latest_rb_ts = _parse_ts(latest_rb_entry.get("ts") or "")
            fresh_recs = [
                r for r in group_recs
                if _parse_ts(r.get("ts") or "") > latest_rb_ts
            ]
        else:
            latest_rb_idx = -1
            latest_rb_entry = None
            fresh_recs = group_recs

        # --- revert-trial (evaluated FIRST — F-D: revert takes precedence over promote) ---
        # F8/F-D: if revert-trial fires, promote rules are suppressed for this group.
        revert_fired = False
        if latest_rb_entry is not None:
            latest_rule = latest_rb_entry.get("rule")
            # F7: use index-based position (latest_rb_idx) not list.index().
            later_reverts = [
                e for i, e in enumerate(rebalance_log)
                if (
                    i > latest_rb_idx
                    and e.get("role") == role
                    and e.get("task_class") == task_class
                    and e.get("rule") == "revert-trial"
                )
            ]
            if latest_rule == "trial-demotion-3x-clean" and not later_reverts:
                # F6: temporal guard — the failing record must be NEWER than
                # the trial-demotion entry itself, not just the latest record.
                demotion_ts = _parse_ts(latest_rb_entry.get("ts") or "")
                failing_recs = [
                    r for r in group_recs
                    if _parse_ts(r.get("ts") or "") > demotion_ts
                    and (
                        r.get("outcome", {}).get("rejects_real", 0) > 0
                        or not r.get("outcome", {}).get("gates_first_try", True)
                    )
                ]
                if failing_recs:
                    revert_to = latest_rb_entry.get("from_model", "")
                    proposals.append({
                        "ts": now,
                        "role": role,
                        "task_class": task_class,
                        "from_model": current_model,
                        "to_model": revert_to,
                        "rule": "revert-trial",
                        "evidence": [failing_recs[-1]["task_id"]],
                    })
                    revert_fired = True

        # F8: per-group flag — at most one promote rule per evaluate_rebalance call.
        # F-D: revert-trial precedence — when revert fired, promote is suppressed.
        promote_fired = revert_fired

        # --- promote-2x-gate-fail ---
        if not promote_fired and len(fresh_recs) >= 2:
            last_two = fresh_recs[-2:]
            if all(
                not rec.get("outcome", {}).get("gates_first_try", True)
                for rec in last_two
            ):
                to_model = _ladder_step_up(current_model, ladder)
                if to_model is not None:
                    proposals.append({
                        "ts": now,
                        "role": role,
                        "task_class": task_class,
                        "from_model": current_model,
                        "to_model": to_model,
                        "rule": "promote-2x-gate-fail",
                        "evidence": [r["task_id"] for r in last_two],
                    })
                    promote_fired = True

        # --- promote-real-p0 ---
        if not promote_fired:
            for rec in fresh_recs:
                if rec.get("outcome", {}).get("p0_escaped") is True:
                    to_model = _ladder_step_up(current_model, ladder)
                    if to_model is not None:
                        proposals.append({
                            "ts": now,
                            "role": role,
                            "task_class": task_class,
                            "from_model": current_model,
                            "to_model": to_model,
                            "rule": "promote-real-p0",
                            "evidence": [rec["task_id"]],
                        })
                        promote_fired = True
                    break  # one proposal per group per evaluate call

        # --- trial-demotion-3x-clean ---
        # Use fresh_recs for the 3x-clean check (F5).
        # A pending trial blocks a new demotion.
        trial_pending = False
        if latest_rb_entry is not None and latest_rb_entry.get("rule") == "trial-demotion-3x-clean":
            # Check no revert-trial exists AFTER the demotion entry (F7: index-based).
            trial_pending = not any(
                i > latest_rb_idx
                and e.get("role") == role
                and e.get("task_class") == task_class
                and e.get("rule") == "revert-trial"
                for i, e in enumerate(rebalance_log)
            )

        # Hard arbitration (G-1a): if any promote or revert rule already fired for
        # this group in this pass, skip the demotion branch entirely.
        # Precedence: revert-trial > promote-2x-gate-fail > promote-real-p0 > trial-demotion.
        if not promote_fired and not trial_pending and len(fresh_recs) >= 3:
            last_three = fresh_recs[-3:]
            all_clean = all(
                # G-1b: p0_escaped disqualifies "clean" — a P0 escape is the opposite.
                not rec.get("outcome", {}).get("p0_escaped")
                and rec.get("outcome", {}).get("review_rounds") == 1
                and rec.get("outcome", {}).get("gates_first_try") is True
                and rec.get("outcome", {}).get("rejects_real", 0) == 0
                for rec in last_three
            )
            if all_clean:
                to_model = _ladder_step_down(current_model, ladder)
                if to_model is not None:
                    proposals.append({
                        "ts": now,
                        "role": role,
                        "task_class": task_class,
                        "from_model": current_model,
                        "to_model": to_model,
                        "rule": "trial-demotion-3x-clean",
                        "evidence": [r["task_id"] for r in last_three],
                    })

    return proposals
