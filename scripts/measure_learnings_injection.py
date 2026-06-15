"""Phase-4 injection-recall measurement instrument.

Measures how many gate-passed Hermes ledger tickets can actually be scope-matched
for injection — distinguishing *file-anchored* tickets (have evidence source_path →
CAN be scope-matched) from *scope-blind* tickets (no evidence files → can NEVER
be injected by the deterministic scope-match regardless of what scopes are listed).

Key metric: ``scope_addressable_pct`` = injected_any_scope / gate_passed_total * 100
              (0.0 when total is 0 OR when all tickets are scope-blind)

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
from _learnings import _ticket_evidence_files, _scope_match
from _mirror_learnings import load_promotable
from _promotion import DEMOTION_THRESHOLD, load_tickets as _load_all_tickets

Ticket = dict[str, Any]

_DEFAULT_SCOPES: list[str] = ["hooks/", "scripts/", "tests/", "docs/"]


def measure(ledger: Path, scopes: list[str]) -> dict[str, Any]:
    """Measure injection-recall for a ledger against a list of scope entries.

    Returns a JSON-able dict with the following PRECISELY-DEFINED keys:

    ``gate_passed_total``
        Count of load_promotable gate-passed tickets.
    ``file_anchored``
        Gate-passed tickets with ≥1 evidence file (``_ticket_evidence_files`` non-empty).
        ONLY these CAN be scope-matched.
    ``scope_blind``
        Gate-passed tickets with NO evidence file.  Can NEVER be injected by scope-match
        regardless of scope.  (= gate_passed_total - file_anchored)
    ``scopes_measured``
        The scopes list passed in.
    ``matched_per_scope``
        {scope: count of gate-passed tickets whose evidence files match that scope}.
    ``injected_any_scope``
        Count of gate-passed tickets matched by ≥1 measured scope.
    ``scope_addressable_pct``
        injected_any_scope / gate_passed_total * 100 (0.0 when total is 0), rounded
        to 1 decimal.
    ``scope_blind_fingerprints``
        Sorted list of ``<fp[:12]>`` for the scope_blind tickets (the G1 hole,
        made explicit).
    """
    if not ledger.exists() or not ledger.is_dir():
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

    _, gate_passed = load_promotable(ledger)

    # Load full ticket set for demotion metrics (partial=True: skip corrupt; never blocks).
    try:
        all_tickets = _load_all_tickets(ledger, partial=True)
    except Exception:
        all_tickets = []

    quarantined_total = sum(1 for t in all_tickets if t.get("state") == "quarantined")
    reinstated_total = sum(
        1 for t in all_tickets if bool(t.get("reinstatements"))
    )
    harmful_pending = sum(
        1 for t in all_tickets
        if t.get("state") != "quarantined"
        and 0 < int(t.get("harmful_count") or 0) < DEMOTION_THRESHOLD
    )

    # Quarantined tickets that WOULD scope-match if promoted (excluded from injection).
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

    for ticket in gate_passed:
        fp = str(ticket.get("fingerprint", ""))
        ev_files = _ticket_evidence_files(ticket)
        if ev_files:
            file_anchored_count += 1
            # Check per-scope
            for scope in scopes:
                if _scope_match([scope], ev_files):
                    matched_per_scope[scope] += 1
                    injected_any.add(fp)
        else:
            scope_blind_fps.append(fp[:12])

        ok, reason = verify_ticket_provenance(ticket, key=_key)
        if reason == "legacy-unsigned":
            prov_legacy += 1
        elif ok:
            prov_verified += 1
        else:
            prov_unverified_fps.append(fp[:12])

    gate_passed_total = len(gate_passed)
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
    p.set_defaults(func=cmd_measure_injection)


def cmd_measure_injection(args: Any) -> int:
    """CLI handler: print JSON measurement of injection-recall for the home ledger."""
    repo_root = Path(getattr(args, "repo_root", ".")).resolve()
    raw_scopes: list[str] | None = getattr(args, "scopes", None)
    scopes = raw_scopes if raw_scopes else list(_DEFAULT_SCOPES)

    ledger = ledger_dir(repo_root, None)
    result = measure(ledger, scopes)
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0
