"""Hermes promotion pipeline (Phase 1): ticket FSM + gate evaluation.

Operates on the home-store ledger written by learning_miner.py. Acting on
a promotable verdict stays human — this module validates and records
transitions, it never decides them. ``promoted`` requires every
promotion_gate field to be True.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

from _contract import atomic_write_text
from _escalation_emit import emit_escalation
from _improvement import ledger_lock, validate_ticket

TRANSITIONS: dict[str, frozenset[str]] = {
    "candidate": frozenset({"accepted", "rejected"}),
    "accepted": frozenset({"implemented", "rejected"}),
    "implemented": frozenset({"verified", "rejected"}),
    "verified": frozenset({"promoted", "rejected"}),
    "promoted": frozenset({"quarantined"}),
    "quarantined": frozenset({"promoted", "rejected"}),
    "rejected": frozenset(),
}
GATE_FIELDS: tuple[str, ...] = ("tests_pass", "ci_pass", "user_approved")

Ticket = dict[str, Any]


class PromotionError(Exception):
    """Illegal transition, unknown ticket/field, or malformed ledger entry."""


class PromotionGateUnmet(PromotionError):
    """Promotion attempted while one or more gate fields are unmet."""


def load_tickets(ledger: Path, *, partial: bool = False) -> list[Ticket]:
    """Load and validate all tickets from ledger dir; skip .lock sidecars.

    When ``partial=True``, malformed tickets are skipped with a stderr warning
    instead of raising; callers that mutate data must use the default
    ``partial=False`` so corrupt entries are never silently processed.
    """
    import sys

    tickets: list[Ticket] = []
    for path in sorted(ledger.glob("*.json")):
        try:
            ticket = json.loads(path.read_text())
            validate_ticket(ticket)
        except Exception as exc:
            if partial:
                print(
                    f"warning: skipping malformed ticket {path.name}: {exc}",
                    file=sys.stderr,
                )
                continue
            raise PromotionError(f"malformed ticket {path.name}: {exc}") from exc
        tickets.append(ticket)
    return tickets


def resolve_fingerprint(ledger: Path, prefix: str) -> str:
    """Resolve a fingerprint prefix to a full fingerprint; raise on ambiguity."""
    matches = [p.stem for p in ledger.glob(f"{prefix}*.json")]
    if not matches:
        raise PromotionError(f"no ticket matches prefix {prefix!r}")
    if len(matches) > 1:
        raise PromotionError(f"ambiguous prefix {prefix!r}: {sorted(matches)}")
    return matches[0]


def _locked_update(ledger: Path, fp: str, mutate: Any) -> Ticket:
    result: Ticket
    lock = ledger / f"{fp}.json.lock"
    with ledger_lock(lock):
        path = ledger / f"{fp}.json"
        if not path.exists():
            raise PromotionError(f"no ticket {fp}")
        try:
            raw: Ticket = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise PromotionError(f"corrupt ticket {fp}: {exc}") from exc
        try:
            validate_ticket(raw)
        except jsonschema.ValidationError as exc:
            raise PromotionError(
                f"ticket {fp} invalid before mutation: {exc.message}"
            ) from exc
        try:
            result = mutate(raw)
        except PromotionError:
            raise
        except KeyError as exc:
            raise PromotionError(f"missing key in ticket {fp}: {exc}") from exc
        try:
            validate_ticket(result)
        except jsonschema.ValidationError as exc:
            raise PromotionError(f"ticket {fp} invalid after mutation: {exc.message}") from exc
        atomic_write_text(path, json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


_TERMINAL_STATES: frozenset[str] = frozenset({"quarantined", "rejected"})


def set_gate_field(ledger: Path, fp: str, field: str, value: bool) -> Ticket:
    """Set one promotion_gate field; raise PromotionError for unknown fields or terminal state."""
    if field not in GATE_FIELDS:
        raise PromotionError(
            f"unknown gate field {field!r}; expected one of {GATE_FIELDS}"
        )

    def mutate(ticket: Ticket) -> Ticket:
        if ticket.get("state") in _TERMINAL_STATES:
            raise PromotionError(
                f"ticket {fp} is in terminal state {ticket['state']!r}; gate mutation denied"
            )
        ticket["promotion_gate"][field] = value
        if value is True:
            ticket["promotion_gate"][f"{field}_at"] = (
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        return ticket

    return _locked_update(ledger, fp, mutate)


def transition(ledger: Path, fp: str, new_state: str) -> Ticket:
    """Transition ticket to new_state; enforce FSM and gate requirements."""
    if new_state not in TRANSITIONS:
        raise PromotionError(f"unknown state {new_state!r}")

    def mutate(ticket: Ticket) -> Ticket:
        current = ticket["state"]
        if new_state not in TRANSITIONS[current]:
            raise PromotionError(f"illegal transition {current} -> {new_state}")
        if new_state == "promoted":
            gate = ticket["promotion_gate"]
            unmet = [f for f in GATE_FIELDS if gate.get(f) is not True]
            if unmet:
                raise PromotionGateUnmet(f"promotion gate unmet: {', '.join(unmet)}")
        ticket["state"] = new_state
        return ticket

    return _locked_update(ledger, fp, mutate)


def register_cli_subparsers(sub: Any) -> None:
    """Register improvements-list/gate/set-state subparsers onto ``sub``."""
    p_il = sub.add_parser("improvements-list")
    p_il.add_argument("--repo-root", default=None, dest="repo_root")
    p_il.add_argument("--json", action="store_true")
    p_il.add_argument("--state", default=None)
    p_il.add_argument("--promotable", action="store_true")
    p_il.set_defaults(func=cmd_improvements_list)

    p_ig = sub.add_parser("improvements-gate")
    p_ig.add_argument("prefix")
    p_ig.add_argument("--field", required=True,
                      choices=list(GATE_FIELDS))
    p_ig.add_argument("--value", required=True, choices=["true", "false"])
    p_ig.add_argument("--repo-root", default=None, dest="repo_root")
    p_ig.set_defaults(func=cmd_improvements_gate)

    p_iss = sub.add_parser("improvements-set-state")
    p_iss.add_argument("prefix")
    p_iss.add_argument("new_state")
    p_iss.add_argument("--repo-root", default=None, dest="repo_root")
    p_iss.set_defaults(func=cmd_improvements_set_state)


def cmd_improvements_list(args: Any) -> int:
    """Print ledger tickets as table or JSON lines."""
    import sys
    from _improvement import ledger_dir

    repo_root = Path(getattr(args, "repo_root", None) or ".")
    ledger = ledger_dir(repo_root, None)
    if not ledger.exists():
        if getattr(args, "json", False):
            pass
        else:
            print("(no ledger)")
        return 0

    try:
        tickets = load_tickets(ledger, partial=True)
    except PromotionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    state_filter = getattr(args, "state", None)
    promotable_only = getattr(args, "promotable", False)

    if state_filter:
        tickets = [t for t in tickets if t.get("state") == state_filter]

    if promotable_only:
        from learning_miner import is_promotable
        tickets = [t for t in tickets if is_promotable(t)]

    if getattr(args, "json", False):
        for t in tickets:
            print(json.dumps(t))
        return 0

    if not tickets:
        print("(no tickets)")
        return 0

    header = f"{'FP':10}  {'PATTERN':30}  {'ASSET':8}  {'RUNS':4}  {'STATE':11}  GATES"
    print(header)
    print("-" * len(header))
    for t in tickets:
        fp_short = str(t.get("fingerprint", ""))[:8]
        pattern = str(t.get("pattern", ""))[:30]
        asset = str(t.get("candidate_asset") or "")[:8]
        runs = str(t.get("distinct_runs", ""))
        state = str(t.get("state", ""))
        gate = t.get("promotion_gate", {})
        gate_summary = ",".join(
            f"{k[0]}={'T' if v is True else 'F' if v is False else '?'}"
            for k, v in gate.items()
        )
        print(f"{fp_short:10}  {pattern:30}  {asset:8}  {runs:4}  {state:11}  {gate_summary}")
    return 0


def cmd_improvements_gate(args: Any) -> int:
    """Set a promotion_gate field on a ticket identified by prefix."""
    import sys
    from _improvement import ledger_dir

    repo_root = Path(getattr(args, "repo_root", None) or ".")
    ledger = ledger_dir(repo_root, None)
    value = args.value.lower() == "true"

    try:
        fp = resolve_fingerprint(ledger, args.prefix)
        out = set_gate_field(ledger, fp, args.field, value)
    except PromotionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    gate = out["promotion_gate"]
    print(json.dumps(gate, indent=2))
    return 0


def cmd_improvements_set_state(args: Any) -> int:
    """Transition a ticket to a new FSM state identified by prefix."""
    import sys
    from _improvement import ledger_dir

    repo_root = Path(getattr(args, "repo_root", None) or ".")
    ledger = ledger_dir(repo_root, None)

    try:
        fp = resolve_fingerprint(ledger, args.prefix)
        out = transition(ledger, fp, args.new_state)
    except PromotionGateUnmet as exc:
        emit_escalation(
            problem_class="promotion-gate-unmet",
            suggested_enrich_query=f"satisfy promotion gate: {exc}",
            approach=f"{getattr(args, 'prefix', '')}->promoted",
            outcome="gate-unmet",
            run_id="",
            snippet=str(exc),
            repo_root=repo_root,
            now=datetime.now(timezone.utc),
        )
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except PromotionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"state: {out['state']}")
    return 0
