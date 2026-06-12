"""Tests for scripts/_rebalance.py — pure rule engine.

Covers: evaluate_rebalance (all four rules + near-miss negatives),
one-proposal-per-group-per-pass arbitration (G-1), and B1 ceiling fix.

Pure-helper tests (normalize_model_token, ladder step, _parse_ts, unknown-model)
live in test_rebalance_helpers.py.

Shared helpers (seed_ledger, ledger_record) live in conftest.py.
Style mirrors tests/test_routing.py: sys.path.insert, direct module import.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _ledger  # noqa: E402

from conftest import ledger_record as _record, seed_ledger as _seed_ledger  # noqa: E402

LADDER = ["fable", "opus", "sonnet", "haiku"]


# ---------------------------------------------------------------------------
# promote-2x-gate-fail
# ---------------------------------------------------------------------------

class TestPromote2xGateFail:
    def test_fires_on_two_consecutive_failures(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record("t1", gates_first_try=False, task_class="feature-multi-file", model="sonnet"),
            _record("t2", gates_first_try=False, task_class="feature-multi-file", model="sonnet"),
        ]
        assert any(p["rule"] == "promote-2x-gate-fail"
                   for p in _ledger.evaluate_rebalance(ledger, LADDER))

    def test_does_not_fire_on_one_failure(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record("t1", gates_first_try=True, task_class="feature-multi-file", model="sonnet"),
            _record("t2", gates_first_try=False, task_class="feature-multi-file", model="sonnet"),
        ]
        assert not any(p["rule"] == "promote-2x-gate-fail"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))

    def test_ladder_top_not_promoted_further(self) -> None:
        # fable (index 0) is already at ceiling.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "fable"}
        ledger["records"] = [
            _record("t1", task_class="feature-multi-file", model="fable", gates_first_try=False),
            _record("t2", task_class="feature-multi-file", model="fable", gates_first_try=False),
        ]
        assert not any(p["rule"] == "promote-2x-gate-fail"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))


# ---------------------------------------------------------------------------
# promote-real-p0
# ---------------------------------------------------------------------------

class TestPromoteRealP0:
    def test_fires_on_p0_escaped(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        rec = _record("t1", task_class="feature-multi-file", model="sonnet", p0_escaped=True)
        ledger["records"] = [rec]
        assert any(p["rule"] == "promote-real-p0"
                   for p in _ledger.evaluate_rebalance(ledger, LADDER))

    def test_does_not_fire_without_p0_escaped(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [_record("t1", task_class="feature-multi-file", model="sonnet")]
        assert not any(p["rule"] == "promote-real-p0"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))


# ---------------------------------------------------------------------------
# trial-demotion-3x-clean
# ---------------------------------------------------------------------------

class TestTrialDemotion3xClean:
    def test_fires_on_three_clean(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record(f"t{i}", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class="feature-multi-file", model="sonnet")
            for i in range(1, 4)
        ]
        assert any(p["rule"] == "trial-demotion-3x-clean"
                   for p in _ledger.evaluate_rebalance(ledger, LADDER))

    def test_does_not_fire_on_two_clean(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record(f"t{i}", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class="feature-multi-file", model="sonnet")
            for i in range(1, 3)
        ]
        assert not any(p["rule"] == "trial-demotion-3x-clean"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))

    def test_blocked_if_trial_pending(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "haiku"}
        ledger["records"] = [
            _record(f"t{i}", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class="feature-multi-file", model="haiku",
                    ts=f"2026-06-12T0{i}:00:00+00:00")
            for i in range(1, 4)
        ]
        ledger["rebalance_log"] = [{
            "ts": "2026-06-11T00:00:00+00:00",
            "role": "worker-primary", "task_class": "feature-multi-file",
            "from_model": "sonnet", "to_model": "haiku",
            "rule": "trial-demotion-3x-clean", "evidence": ["t0"],
        }]
        assert not any(p["rule"] == "trial-demotion-3x-clean"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))

    def test_ladder_bottom_not_demoted_further(self) -> None:
        # haiku (last) is already at floor.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "haiku"}
        ledger["records"] = [
            _record(f"t{i}", task_class="feature-multi-file", model="haiku",
                    gates_first_try=True, review_rounds=1, rejects_real=0)
            for i in range(1, 4)
        ]
        assert not any(p["rule"] == "trial-demotion-3x-clean"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))

    def test_p0_escaped_disqualifies_clean_window(self) -> None:
        # G-1b: p0_escaped=True in any record makes its window NOT all-clean.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record("t1", gates_first_try=True, review_rounds=1, rejects_real=0,
                    p0_escaped=True, task_class="feature-multi-file", model="sonnet"),
            _record("t2", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class="feature-multi-file", model="sonnet"),
            _record("t3", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class="feature-multi-file", model="sonnet"),
        ]
        assert not any(p["rule"] == "trial-demotion-3x-clean"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))


# ---------------------------------------------------------------------------
# revert-trial
# ---------------------------------------------------------------------------

class TestRevertTrial:
    def test_fires_on_bad_record_after_demotion(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "haiku"}
        ledger["records"] = [
            _record("t1", gates_first_try=False, review_rounds=2, rejects_real=1,
                    task_class="feature-multi-file", model="haiku",
                    ts="2026-06-12T01:00:00+00:00"),
        ]
        ledger["rebalance_log"] = [{
            "ts": "2026-06-11T00:00:00+00:00",
            "role": "worker-primary", "task_class": "feature-multi-file",
            "from_model": "sonnet", "to_model": "haiku",
            "rule": "trial-demotion-3x-clean", "evidence": ["t0"],
        }]
        assert any(p["rule"] == "revert-trial"
                   for p in _ledger.evaluate_rebalance(ledger, LADDER))

    def test_does_not_fire_if_already_reverted(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record("t1", gates_first_try=False, rejects_real=1,
                    task_class="feature-multi-file", model="haiku",
                    ts="2026-06-12T01:00:00+00:00"),
        ]
        ledger["rebalance_log"] = [
            {
                "ts": "2026-06-10T00:00:00+00:00",
                "role": "worker-primary", "task_class": "feature-multi-file",
                "from_model": "sonnet", "to_model": "haiku",
                "rule": "trial-demotion-3x-clean", "evidence": ["t0"],
            },
            {
                "ts": "2026-06-11T00:00:00+00:00",
                "role": "worker-primary", "task_class": "feature-multi-file",
                "from_model": "haiku", "to_model": "sonnet",
                "rule": "revert-trial", "evidence": ["t1"],
            },
        ]
        assert not any(p["rule"] == "revert-trial"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))


# ---------------------------------------------------------------------------
# F5: re-run idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_no_duplicate_proposals_on_rerun(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "opus"}
        ledger["records"] = [
            _record(f"t{i}", gates_first_try=False, task_class="feature-multi-file",
                    model="sonnet", ts=f"2026-06-12T0{i}:00:00+00:00")
            for i in range(1, 3)
        ]
        ledger["rebalance_log"] = [{
            "ts": "2026-06-12T03:00:00+00:00",
            "role": "worker-primary", "task_class": "feature-multi-file",
            "from_model": "sonnet", "to_model": "opus",
            "rule": "promote-2x-gate-fail", "evidence": ["t1", "t2"],
        }]
        assert not any(p["rule"] == "promote-2x-gate-fail"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))


# ---------------------------------------------------------------------------
# F6: revert-trial temporal guard
# ---------------------------------------------------------------------------

class TestRevertTemporalGuard:
    def test_revert_only_fires_for_records_after_demotion(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "haiku"}
        # Failing record BEFORE the trial demotion must not trigger revert.
        ledger["records"] = [
            _record("t0", gates_first_try=False, rejects_real=1,
                    task_class="feature-multi-file", model="haiku",
                    ts="2026-06-10T00:00:00+00:00"),
        ]
        ledger["rebalance_log"] = [{
            "ts": "2026-06-11T00:00:00+00:00",
            "role": "worker-primary", "task_class": "feature-multi-file",
            "from_model": "sonnet", "to_model": "haiku",
            "rule": "trial-demotion-3x-clean", "evidence": ["t_clean"],
        }]
        assert not any(p["rule"] == "revert-trial"
                       for p in _ledger.evaluate_rebalance(ledger, LADDER))


# ---------------------------------------------------------------------------
# F8: double-promote prevention
# ---------------------------------------------------------------------------

class TestDoublePromotePrevention:
    def test_at_most_one_promote_rule_per_group(self) -> None:
        # Both promote-2x-gate-fail AND promote-real-p0 conditions met.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record("t1", gates_first_try=False, task_class="feature-multi-file",
                    model="sonnet", p0_escaped=True),
            _record("t2", gates_first_try=False, task_class="feature-multi-file",
                    model="sonnet"),
        ]
        promote_proposals = [
            p for p in _ledger.evaluate_rebalance(ledger, LADDER)
            if p["role"] == "worker-primary" and p["rule"].startswith("promote")
        ]
        assert len(promote_proposals) == 1


# ---------------------------------------------------------------------------
# F9: composite key assignments
# ---------------------------------------------------------------------------

class TestCompositeKeyAssignments:
    def test_composite_key_preferred_over_role_key(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "opus"}
        ledger["assignments"]["worker-primary/feature-multi-file"] = {"model": "sonnet"}
        ledger["records"] = [
            _record(f"t{i}", gates_first_try=False, task_class="feature-multi-file",
                    model="sonnet")
            for i in range(1, 3)
        ]
        promote = next(
            (p for p in _ledger.evaluate_rebalance(ledger, LADDER)
             if p["rule"] == "promote-2x-gate-fail"), None
        )
        assert promote is not None
        assert promote["from_model"] == "sonnet"


# ---------------------------------------------------------------------------
# F-D: revert-trial suppresses promote
# ---------------------------------------------------------------------------

class TestRevertSuppressesPromote:
    def test_revert_trial_suppresses_promote_same_group(self) -> None:
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "haiku"}
        ledger["records"] = [
            _record("t1", gates_first_try=False, rejects_real=1,
                    task_class="feature-multi-file", model="haiku",
                    ts="2026-06-12T01:00:00+00:00"),
            _record("t2", gates_first_try=False, rejects_real=0,
                    task_class="feature-multi-file", model="haiku",
                    ts="2026-06-12T02:00:00+00:00"),
        ]
        ledger["rebalance_log"] = [{
            "ts": "2026-06-11T00:00:00+00:00",
            "role": "worker-primary", "task_class": "feature-multi-file",
            "from_model": "sonnet", "to_model": "haiku",
            "rule": "trial-demotion-3x-clean", "evidence": ["t0"],
        }]
        proposals = _ledger.evaluate_rebalance(ledger, LADDER)
        group = [p for p in proposals
                 if p["role"] == "worker-primary" and p["task_class"] == "feature-multi-file"]
        rules = [p["rule"] for p in group]
        assert "revert-trial" in rules
        assert not any(r.startswith("promote") for r in rules)
        assert len(group) == 1


# ---------------------------------------------------------------------------
# G-1 — one-proposal-per-group-per-pass arbitration
# ---------------------------------------------------------------------------

class TestOneProposalPerGroupPerPass:
    def test_promote_blocks_demotion_in_same_pass(self) -> None:
        # G-1a: promote-real-p0 fires → trial-demotion must NOT fire in same pass.
        # 3 fresh records; one has p0_escaped — promote fires + blocks demotion.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record("t1", gates_first_try=True, review_rounds=1, rejects_real=0,
                    p0_escaped=True, task_class="feature-multi-file", model="sonnet",
                    ts="2026-06-12T01:00:00+00:00"),
            _record("t2", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class="feature-multi-file", model="sonnet",
                    ts="2026-06-12T02:00:00+00:00"),
            _record("t3", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class="feature-multi-file", model="sonnet",
                    ts="2026-06-12T03:00:00+00:00"),
        ]
        proposals = _ledger.evaluate_rebalance(ledger, LADDER)
        assert any(p["rule"] == "promote-real-p0" for p in proposals)
        assert not any(p["rule"] == "trial-demotion-3x-clean" for p in proposals)

    def test_p0_escaped_record_excluded_from_clean_count(self) -> None:
        # G-1b: p0_escaped record in the window → window not all-clean; demotion blocked.
        # The p0_escaped also fires promote, so both G-1a and G-1b apply here.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        ledger["records"] = [
            _record("t1", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class="feature-multi-file", model="sonnet"),
            _record("t2", gates_first_try=True, review_rounds=1, rejects_real=0,
                    p0_escaped=True, task_class="feature-multi-file", model="sonnet"),
            _record("t3", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class="feature-multi-file", model="sonnet"),
        ]
        proposals = _ledger.evaluate_rebalance(ledger, LADDER)
        # promote-real-p0 fires (t2.p0_escaped), disqualifying the clean window.
        assert any(p["rule"] == "promote-real-p0" for p in proposals)
        assert not any(p["rule"] == "trial-demotion-3x-clean" for p in proposals)

    def test_at_most_one_proposal_per_group_structural_invariant(self) -> None:
        # G-1 hard invariant: ≤1 proposal per (role, task_class) group per call.
        # Multi-rule scenario: 2x gate fails + p0_escaped + 3 clean-looking records.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "sonnet"}
        role, tc = "worker-primary", "feature-multi-file"
        ledger["records"] = [
            _record("t1", gates_first_try=False, review_rounds=1, rejects_real=0,
                    p0_escaped=True, task_class=tc, model="sonnet",
                    ts="2026-06-12T01:00:00+00:00"),
            _record("t2", gates_first_try=False, review_rounds=1, rejects_real=0,
                    task_class=tc, model="sonnet",
                    ts="2026-06-12T02:00:00+00:00"),
            _record("t3", gates_first_try=True, review_rounds=1, rejects_real=0,
                    task_class=tc, model="sonnet",
                    ts="2026-06-12T03:00:00+00:00"),
        ]
        group = [p for p in _ledger.evaluate_rebalance(ledger, LADDER)
                 if p["role"] == role and p["task_class"] == tc]
        assert len(group) <= 1, (
            f"expected ≤1 proposal per group per pass; got {len(group)}: "
            f"{[p['rule'] for p in group]}"
        )


# ---------------------------------------------------------------------------
# B1: promote-signal at ceiling must NOT produce a demotion proposal
# ---------------------------------------------------------------------------

class TestPromoteCeilingArbitration:
    """B1 correctness fix: promote signal at ceiling must set arbitration flag.

    When the group is at ladder ceiling, _ladder_step_up returns None → no
    promote proposal emitted.  Without the fix, promote_fired stays False →
    trial-demotion fires on the same evidence → wrong direction change.
    """

    def test_p0_escaped_at_ceiling_yields_no_proposals(self) -> None:
        # B1 primary regression: fable at ceiling + p0_escaped older record +
        # 3 clean newer records → demotion MUST NOT fire (promote signal blocks it).
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "fable"}
        ledger["records"] = [
            _record("t_p0", model="fable", task_class="feature-multi-file",
                    gates_first_try=True, review_rounds=1, rejects_real=0,
                    p0_escaped=True, ts="2026-06-12T01:00:00+00:00"),
            _record("t_c1", model="fable", task_class="feature-multi-file",
                    gates_first_try=True, review_rounds=1, rejects_real=0,
                    ts="2026-06-12T02:00:00+00:00"),
            _record("t_c2", model="fable", task_class="feature-multi-file",
                    gates_first_try=True, review_rounds=1, rejects_real=0,
                    ts="2026-06-12T03:00:00+00:00"),
            _record("t_c3", model="fable", task_class="feature-multi-file",
                    gates_first_try=True, review_rounds=1, rejects_real=0,
                    ts="2026-06-12T04:00:00+00:00"),
        ]
        proposals = _ledger.evaluate_rebalance(ledger, LADDER)
        group = [p for p in proposals
                 if p["role"] == "worker-primary" and p["task_class"] == "feature-multi-file"]
        rules = [p["rule"] for p in group]
        assert "trial-demotion-3x-clean" not in rules, (
            f"BUG: demotion fired despite promote signal at ceiling: {rules}"
        )
        assert not any(r.startswith("promote") for r in rules), (
            f"Unexpected promote proposal at ceiling: {rules}"
        )
        assert len(group) == 0, f"Expected 0 proposals, got {len(group)}: {rules}"

    def test_2x_gate_fail_at_ceiling_yields_no_proposals(self) -> None:
        # B1 variant: 2x consecutive gate-fail at ceiling → no demotion (signal blocks).
        # Gate-fail records are the LAST two so promote-2x-gate-fail detects the signal.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "fable"}
        ledger["records"] = [
            _record("t_c1", model="fable", task_class="feature-multi-file",
                    gates_first_try=True, review_rounds=1, rejects_real=0,
                    ts="2026-06-12T01:00:00+00:00"),
            _record("t_g1", model="fable", task_class="feature-multi-file",
                    gates_first_try=False, ts="2026-06-12T02:00:00+00:00"),
            _record("t_g2", model="fable", task_class="feature-multi-file",
                    gates_first_try=False, ts="2026-06-12T03:00:00+00:00"),
        ]
        proposals = _ledger.evaluate_rebalance(ledger, LADDER)
        group = [p for p in proposals
                 if p["role"] == "worker-primary" and p["task_class"] == "feature-multi-file"]
        rules = [p["rule"] for p in group]
        assert "trial-demotion-3x-clean" not in rules, (
            f"BUG: demotion fired despite 2x-gate-fail signal at ceiling: {rules}"
        )
        assert not any(r.startswith("promote") for r in rules), (
            f"Unexpected promote proposal at ceiling: {rules}"
        )
        assert len(group) == 0, f"Expected 0 proposals, got {len(group)}: {rules}"

    def test_p0_not_at_ceiling_still_promotes(self) -> None:
        # Guard: p0_escaped with opus (not ceiling) → promote fires, demotion suppressed.
        ledger = _seed_ledger()
        ledger["assignments"]["worker-primary"] = {"model": "opus"}
        ledger["records"] = [
            _record("t_p0", model="opus", task_class="feature-multi-file",
                    gates_first_try=True, review_rounds=1, rejects_real=0,
                    p0_escaped=True, ts="2026-06-12T01:00:00+00:00"),
            _record("t_c1", model="opus", task_class="feature-multi-file",
                    gates_first_try=True, review_rounds=1, rejects_real=0,
                    ts="2026-06-12T02:00:00+00:00"),
            _record("t_c2", model="opus", task_class="feature-multi-file",
                    gates_first_try=True, review_rounds=1, rejects_real=0,
                    ts="2026-06-12T03:00:00+00:00"),
            _record("t_c3", model="opus", task_class="feature-multi-file",
                    gates_first_try=True, review_rounds=1, rejects_real=0,
                    ts="2026-06-12T04:00:00+00:00"),
        ]
        proposals = _ledger.evaluate_rebalance(ledger, LADDER)
        group = [p for p in proposals
                 if p["role"] == "worker-primary" and p["task_class"] == "feature-multi-file"]
        rules = [p["rule"] for p in group]
        assert "promote-real-p0" in rules, f"Expected promote-real-p0, got {rules}"
        assert "trial-demotion-3x-clean" not in rules, (
            f"Demotion must be suppressed when promote fires: {rules}"
        )
        assert len(group) == 1, f"Expected exactly 1 proposal, got {len(group)}: {rules}"
