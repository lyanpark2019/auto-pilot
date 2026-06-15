"""Phase-4 injection-recall measurement instrument + gate-vs-ungated A/B.

Measures how many gate-passed Hermes ledger tickets can actually be scope-matched
for injection — distinguishing *file-anchored* tickets (have evidence source_path →
CAN be scope-matched) from *scope-blind* tickets (no evidence files → can NEVER
be injected by the deterministic scope-match regardless of what scopes are listed).

Key metric: ``scope_addressable_pct`` = injected_any_scope / gate_passed_total * 100
              (0.0 when total is 0 OR when all tickets are scope-blind)

``compare_gating`` adds the A/B view: what the gate FILTERS OUT vs what would leak
in without it.  Both arms share the same ticket load; the gate arm applies
``is_gate_passed``; the ungated arm skips it.

ADR 0002: injection reads the Ledger, never vault prose.
Reuses ``load_promotable`` from ``_mirror_learnings`` (authoritative gate-passed load)
and ``_ticket_evidence_files`` + ``_scope_match`` from ``_learnings`` (single-source
of the evidence/scope convention).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from _improvement import ledger_dir, local_key, verify_ticket_provenance
from _learnings import (
    _EXCLUDED_STATES,
    _scope_match,
    _ticket_evidence_files,
    is_gate_passed,
)
from _mirror_learnings import load_promotable
from _promotion import DEMOTION_THRESHOLD, load_tickets as _load_all_tickets

Ticket = dict[str, Any]

_DEFAULT_SCOPES: list[str] = ["hooks/", "scripts/", "tests/", "docs/"]

# Top-level numeric scalars compared by measure_delta.
_SCALAR_KEYS = (
    "file_anchored",
    "gate_passed_total",
    "injected_any_scope",
    "provenance_legacy_unsigned",
    "provenance_unverified",
    "provenance_verified",
    "scope_addressable_pct",
    "scope_blind",
)


def _empty_result(scopes: list[str]) -> dict[str, Any]:
    return {
        "gate_passed_total": 0,
        "file_anchored": 0,
        "scope_blind": 0,
        "scopes_measured": scopes,
        "matched_per_scope": {s: 0 for s in scopes},
        "injected_any_scope": 0,
        "scope_addressable_pct": 0.0,
        "scope_blind_fingerprints": [],
        "provenance_verified": 0,
        "provenance_legacy_unsigned": 0,
        "provenance_unverified": 0,
        "provenance_filtered_pct": 0.0,
        "filtered_fingerprints": [],
        "quarantined_total": 0,
        "demoted_excluded_from_injection": 0,
        "harmful_pending": 0,
        "reinstated_total": 0,
    }


def _prov_bucket(
    ticket: Ticket, key: bytes
) -> tuple[bool, bool, bool]:
    """Return (verified, legacy_unsigned, unverified) booleans for one ticket."""
    ok, reason = verify_ticket_provenance(ticket, key=key)
    if reason == "legacy-unsigned":
        return (False, True, False)
    if ok:
        return (True, False, False)
    return (False, False, True)


def measure(
    ledger: Path,
    scopes: list[str],
    *,
    gated: bool = True,
) -> dict[str, Any]:
    """Measure injection-recall for a ledger against a list of scope entries.

    When ``gated=True`` (default), only gate-passed tickets count — this is the
    production view and produces the EXACT same output as prior versions (back-compat).
    When ``gated=False``, ALL scope-matchable tickets are counted regardless of gate
    state — the ungated arm for A/B comparison.

    Returns a JSON-able dict with the following PRECISELY-DEFINED keys:

    ``gate_passed_total``
        Count of tickets in the measured population (gate-passed or all when ungated).
    ``file_anchored``
        Population tickets with ≥1 evidence file.  ONLY these CAN be scope-matched.
    ``scope_blind``
        Population tickets with NO evidence file.  Can NEVER be injected by scope-match.
    ``scopes_measured``
        The scopes list passed in.
    ``matched_per_scope``
        {scope: count of population tickets whose evidence files match that scope}.
    ``injected_any_scope``
        Count of population tickets matched by ≥1 measured scope.
    ``scope_addressable_pct``
        injected_any_scope / gate_passed_total * 100 (0.0 when total is 0), rounded
        to 1 decimal.
    ``scope_blind_fingerprints``
        Sorted list of ``<fp[:12]>`` for the scope_blind tickets.
    """
    if not ledger.exists() or not ledger.is_dir():
        return _empty_result(scopes)

    if gated:
        _, gate_passed = load_promotable(ledger)
        population = gate_passed
    else:
        try:
            population = _load_all_tickets(ledger, partial=True)
        except Exception:
            population = []

    try:
        all_tickets = _load_all_tickets(ledger, partial=True)
    except Exception:
        all_tickets = []

    quarantined_total = sum(1 for t in all_tickets if t.get("state") == "quarantined")
    reinstated_total = sum(1 for t in all_tickets if bool(t.get("reinstatements")))
    harmful_pending = sum(
        1 for t in all_tickets
        if t.get("state") != "quarantined"
        and 0 < int(t.get("harmful_count") or 0) < DEMOTION_THRESHOLD
    )
    demoted_excluded = 0
    for t in all_tickets:
        if t.get("state") != "quarantined":
            continue
        ev_files = _ticket_evidence_files(t)
        if ev_files and _scope_match(list(scopes), ev_files):
            demoted_excluded += 1

    _key = local_key()
    file_anchored_count = 0
    scope_blind_fps: list[str] = []
    matched_per_scope: dict[str, int] = {s: 0 for s in scopes}
    injected_any: set[str] = set()
    prov_verified = 0
    prov_legacy = 0
    prov_unverified_fps: list[str] = []

    for ticket in population:
        fp = str(ticket.get("fingerprint", ""))
        ev_files = _ticket_evidence_files(ticket)
        if ev_files:
            file_anchored_count += 1
            for scope in scopes:
                if _scope_match([scope], ev_files):
                    matched_per_scope[scope] += 1
                    injected_any.add(fp)
        else:
            scope_blind_fps.append(fp[:12])

        verified, legacy, unverified = _prov_bucket(ticket, _key)
        if legacy:
            prov_legacy += 1
        elif verified:
            prov_verified += 1
        else:
            prov_unverified_fps.append(fp[:12])

    gate_passed_total = len(population)
    scope_blind_count = gate_passed_total - file_anchored_count
    injected_any_scope = len(injected_any)
    prov_unverified = len(prov_unverified_fps)

    if gate_passed_total == 0:
        pct = 0.0
        filtered_pct = 0.0
    else:
        pct = round(injected_any_scope / gate_passed_total * 100, 1)
        filtered_pct = round(prov_unverified / gate_passed_total * 100, 1)

    return {
        "gate_passed_total": gate_passed_total,
        "file_anchored": file_anchored_count,
        "scope_blind": scope_blind_count,
        "scopes_measured": scopes,
        "matched_per_scope": matched_per_scope,
        "injected_any_scope": injected_any_scope,
        "scope_addressable_pct": pct,
        "scope_blind_fingerprints": sorted(scope_blind_fps),
        "provenance_verified": prov_verified,
        "provenance_legacy_unsigned": prov_legacy,
        "provenance_unverified": prov_unverified,
        "provenance_filtered_pct": filtered_pct,
        "filtered_fingerprints": sorted(prov_unverified_fps),
        "quarantined_total": quarantined_total,
        "demoted_excluded_from_injection": demoted_excluded,
        "harmful_pending": harmful_pending,
        "reinstated_total": reinstated_total,
    }


def measure_delta(
    baseline: dict[str, Any],
    variant: dict[str, Any],
) -> dict[str, Any]:
    """Compute A/B delta between two measure() output dicts.

    Covers the comparable top-level scalars defined in ``_SCALAR_KEYS``.
    Non-comparable keys (``matched_per_scope``, ``scope_blind_fingerprints``,
    ``filtered_fingerprints``, ``scopes_measured``, ``provenance_filtered_pct``,
    ``quarantined_total``, ``demoted_excluded_from_injection``,
    ``harmful_pending``, ``reinstated_total``) are omitted — they differ in
    structure or semantics between gated and ungated.

    Returns ``{metric: {"a": <baseline>, "b": <variant>, "delta": <b - a>}}``
    with sorted keys for byte-stable serialisation.
    """
    delta: dict[str, Any] = {}
    for key in _SCALAR_KEYS:
        a_val = float(baseline.get(key, 0))
        b_val = float(variant.get(key, 0))
        delta[key] = {"a": a_val, "b": b_val, "delta": b_val - a_val}
    return dict(sorted(delta.items()))


def _provenance_counts(
    fingerprints: set[str],
    all_tickets: list[Ticket],
    key: bytes,
) -> dict[str, int]:
    """Summarise provenance status for a set of fingerprints."""
    fp_map = {str(t.get("fingerprint", "")): t for t in all_tickets}
    verified = 0
    legacy_unsigned = 0
    unverified = 0
    for fp in fingerprints:
        ticket = fp_map.get(fp)
        if ticket is None:
            unverified += 1
            continue
        v, leg, u = _prov_bucket(ticket, key)
        if leg:
            legacy_unsigned += 1
        elif v:
            verified += 1
        else:
            unverified += 1
    return {"legacy_unsigned": legacy_unsigned, "unverified": unverified, "verified": verified}


def compare_gating(ledger: Path, scopes: list[str]) -> dict[str, Any]:
    """A/B comparison: what the gate admits vs what it filters out.

    Loads all tickets ONCE; computes injected-fingerprint SETS for both arms:
    - gated: ``is_gate_passed`` AND scope-match
    - ungated: scope-match only (no gate filter)

    Returns a JSON-able dict (sorted keys, byte-stable across ledger file order):

    ``delta``
        ``measure_delta(gated_measure, ungated_measure)`` — per-scalar {a, b, delta}.
    ``filtered_total``
        Count of tickets the gate filters out that would otherwise be injected.
    ``filtered_breakdown``
        ``{"excluded_state": int, "not_promotable": int}`` — per-reason partition
        of ``filtered_total``.  ``excluded_state`` = state ∈ {rejected, quarantined};
        ``not_promotable`` = sub-threshold or un-promoted (everything else the gate rejects).
    ``filtered_fingerprints``
        Sorted ``fp[:12]`` of the filtered set.
    ``gated_provenance``
        ``{"verified", "legacy_unsigned", "unverified"}`` for the gated injected set.
    ``ungated_provenance``
        Same shape for the ungated injected set — shows extra unverified-provenance
        tickets the gate would have blocked.
    ``scopes_measured``
        The scopes list used.

    Note on denominators: ``delta.provenance_*`` fields are computed over the
    full gate-passed/ungated POPULATION (same denominator as ``measure()``),
    whereas ``gated_provenance`` and ``ungated_provenance`` are over each arm's
    scope-matched INJECTED SET only — a strictly smaller subset.  Reading
    ``legacy_unsigned: 3`` in ``delta`` vs ``2`` in ``gated_provenance`` is not
    a contradiction: the delta counts all gate-passed tickets; the provenance
    dict counts only those that were also scope-matched for injection.
    """
    if not ledger.exists() or not ledger.is_dir():
        empty_prov = {"legacy_unsigned": 0, "unverified": 0, "verified": 0}
        return {
            "delta": measure_delta(_empty_result(scopes), _empty_result(scopes)),
            "filtered_breakdown": {"excluded_state": 0, "not_promotable": 0},
            "filtered_fingerprints": [],
            "filtered_total": 0,
            "gated_provenance": empty_prov,
            "scopes_measured": scopes,
            "ungated_provenance": empty_prov,
        }

    try:
        all_tickets = _load_all_tickets(ledger, partial=True)
    except Exception:
        all_tickets = []

    _key = local_key()
    gated_injected: set[str] = set()
    ungated_injected: set[str] = set()

    for ticket in all_tickets:
        fp = str(ticket.get("fingerprint", ""))
        ev_files = _ticket_evidence_files(ticket)
        if not ev_files:
            continue
        if not _scope_match(scopes, ev_files):
            continue
        ungated_injected.add(fp)
        if is_gate_passed(ticket):
            gated_injected.add(fp)

    filtered_fps = ungated_injected - gated_injected

    fp_map = {str(t.get("fingerprint", "")): t for t in all_tickets}
    excluded_state = 0
    not_promotable = 0
    for fp in filtered_fps:
        t = fp_map.get(fp)
        if t is not None and t.get("state") in _EXCLUDED_STATES:
            excluded_state += 1
        else:
            not_promotable += 1

    gated_measure = measure(ledger, scopes, gated=True)
    ungated_measure = measure(ledger, scopes, gated=False)

    return dict(sorted({
        "delta": measure_delta(gated_measure, ungated_measure),
        "filtered_breakdown": {
            "excluded_state": excluded_state,
            "not_promotable": not_promotable,
        },
        "filtered_fingerprints": sorted(fp[:12] for fp in filtered_fps),
        "filtered_total": len(filtered_fps),
        "gated_provenance": _provenance_counts(gated_injected, all_tickets, _key),
        "scopes_measured": scopes,
        "ungated_provenance": _provenance_counts(ungated_injected, all_tickets, _key),
    }.items()))


def register_cli_subparsers(sub: Any) -> None:
    """Register ``measure-injection`` onto the orchestrator CLI parser."""
    p = sub.add_parser("measure-injection")
    p.add_argument(
        "--repo-root", default=".", dest="repo_root",
        help="project root (default: .); used to resolve the home ledger",
    )
    p.add_argument(
        "--scope", action="append", dest="scopes", default=None, metavar="SCOPE",
        help=(
            "scope entry to measure (repeatable; trailing '/' = dir prefix). "
            f"Default: {_DEFAULT_SCOPES}"
        ),
    )
    p.add_argument(
        "--json", action="store_true", dest="output_json",
        help="output pretty JSON (always true; flag kept for compat)",
    )
    p.add_argument(
        "--compare-gating", action="store_true", dest="compare_gating",
        help=(
            "Run gate-vs-ungated A/B: show what the gate filters out vs what would "
            "leak in without it.  Prints compare_gating() JSON and exits."
        ),
    )
    p.set_defaults(func=cmd_measure_injection)


def cmd_measure_injection(args: Any) -> int:
    """CLI handler: print JSON measurement of injection-recall for the home ledger."""
    repo_root = Path(getattr(args, "repo_root", ".")).resolve()
    raw_scopes: list[str] | None = getattr(args, "scopes", None)
    scopes = raw_scopes if raw_scopes else list(_DEFAULT_SCOPES)

    ledger = ledger_dir(repo_root, None)

    if getattr(args, "compare_gating", False):
        result = compare_gating(ledger, scopes)
        sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 0

    result = measure(ledger, scopes)
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0
