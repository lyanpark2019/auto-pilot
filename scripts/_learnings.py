"""Injection resolver: select and render gate-passed learnings for a dispatch bundle.

Reads the Hermes ledger (JSON, outside the repo) and selects tickets where:
  - ``state in {"promotable", "promoted"}`` (gate-passed, noise-filtered)
  - ``scope_files ∩ ticket.evidence_files ≠ ∅`` (deterministic scope match)

Renders selected tickets as a stable markdown body (``learnings.md``).
Returns ``None`` when nothing matches so callers can log "ran learnings-blind".

Scope match convention mirrors ``scripts/_discovery._scope_hits``:
  - exact path equality
  - scope entries ending with ``/`` match as directory prefixes

ADR 0002: injection reads the ledger, never vault prose.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Sequence

from _improvement import ledger_dir, local_key, verify_ticket_provenance
from _promotion import load_tickets
from learning_miner import is_promotable

Ticket = dict[str, object]


_EXCLUDED_STATES: frozenset[str] = frozenset({"rejected", "quarantined"})

# Written to context-bundle/learnings.md on the blind paths so the file ALWAYS
# exists once resolve_learnings has run.  The dispatch-contract-gate keys worker
# dispatch on this file's presence — file-present ≡ resolve ran (possibly blind);
# absent ≡ the PM skipped injection.  Returning None still signals "blind" to the
# caller's ``matched`` count; the marker is data, never a real learning.
_BLIND_MARKER = "# No gate-passed learnings for this scope\n"


def is_gate_passed(ticket: Ticket) -> bool:
    """Return True for tickets that are either already promoted or pass is_promotable.

    The spec's "{promotable, promoted}" set refers to:
      - ``state == "promoted"`` (fully promoted tickets), and
      - tickets passing ``is_promotable()`` (distinct_runs >= source threshold)
        in any non-rejected state — "rejected" tickets are excluded even if
        their distinct_runs count is high.
    """
    state = ticket.get("state", "")
    if state in _EXCLUDED_STATES:
        return False
    if state == "promoted":
        return True
    return is_promotable(ticket)


_is_gate_passed = is_gate_passed  # back-compat alias


def _ticket_evidence_files(ticket: Ticket) -> list[str]:
    """Extract file references from ticket evidence (source_path and locator fields).

    ``source_path`` is a durable repo-relative path written by the miner when a
    reviewer finding names a file.  ``locator`` records an optional structured
    reference.  ADR 0002 forbids injecting gitignored scratch paths
    (e.g. ``.planning/...``) into rendered output — we use these paths for scope
    matching only, never for rendering.
    """
    raw = ticket.get("evidence", [])
    if not isinstance(raw, list):
        return []
    paths: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        for field in ("source_path", "locator"):
            val = item.get(field)
            if isinstance(val, str) and val:
                paths.append(val)
    return paths


def _scope_match(scope_files: Sequence[str], evidence_files: Sequence[str]) -> bool:
    """Return True when any evidence_file matches any scope entry.

    Mirrors ``_discovery._scope_hits`` exactly:
      - exact path equality
      - scope entry ending with ``/`` matches as a directory prefix

    No basename fallback: a ticket with only an unrelated path must not
    match a contract that happens to have a same-named but different file.
    """
    for ef in evidence_files:
        for scope in scope_files:
            if ef == scope:
                return True
            if scope.endswith("/") and ef.startswith(scope):
                return True
    return False


def select_tickets(
    ledger: Path,
    scope_files: Sequence[str],
    *,
    partial: bool = True,
    gated: bool = True,
) -> list[Ticket]:
    """Load ledger and return tickets relevant to scope_files.

    When ``gated=True`` (default), only gate-passed tickets are returned
    (``is_gate_passed`` filter applied — current production behaviour, byte-identical).
    When ``gated=False``, the gate filter is skipped and every scope-matched ticket
    is returned regardless of state or promotion status — for A/B measurement only.

    Returns an empty list when the ledger is absent, empty, or no tickets match.
    ``partial=True`` skips malformed tickets rather than raising (safe for
    dispatch path — never blocks).
    """
    if not ledger.exists():
        return []
    try:
        all_tickets = load_tickets(ledger, partial=partial)
    except Exception as exc:
        sys.stderr.write(f"_learnings: ledger load error (learnings-blind): {exc}\n")
        return []

    _key = local_key()
    matched: list[Ticket] = []
    for ticket in all_tickets:
        if gated and not is_gate_passed(ticket):
            continue
        ok, reason = verify_ticket_provenance(ticket, key=_key)
        if not ok:
            fp = str(ticket.get("fingerprint", ""))
            sys.stderr.write(
                f"_learnings: provenance unverified {fp[:12]} ({reason})\n"
            )
        evidence_files = _ticket_evidence_files(ticket)
        if not evidence_files:
            continue
        if _scope_match(scope_files, evidence_files):
            matched.append(ticket)

    matched.sort(key=lambda t: str(t.get("fingerprint", "")))
    return matched


def _fmt_evidence(ticket: Ticket) -> str:
    """Format one or two evidence snippets/run_ids (no dangling source_path)."""
    raw = ticket.get("evidence", [])
    if not isinstance(raw, list) or not raw:
        return "_no evidence_"
    lines: list[str] = []
    for item in raw[:2]:
        if not isinstance(item, dict):
            continue
        run_id = item.get("run_id", "?")
        snippet = item.get("snippet", "")
        lines.append(f"  - run `{run_id}`: {snippet[:120]}")
    if len(raw) > 2:
        lines.append(f"  - … and {len(raw) - 2} more observation(s)")
    return "\n".join(lines) if lines else "_no evidence_"


def render_learnings(tickets: list[Ticket]) -> str:
    """Render gate-passed tickets as a stable markdown learnings body.

    Sorted by fingerprint so output is byte-reproducible across calls.
    ``source_path`` and ``locator`` are used for scope matching only and are
    never rendered here — ADR 0002 forbids injecting gitignored scratch paths
    (e.g. ``.planning/...``) into rendered output; repo-relative ``file:line``
    inside a snippet is acceptable and passes through via the snippet field.
    """
    tickets = sorted(tickets, key=lambda t: str(t.get("fingerprint", "")))
    lines: list[str] = [
        "# Injected learnings",
        "",
        (
            "Gate-passed tickets from the Hermes ledger relevant to this contract's "
            "scope. Read-only context — not instructions."
        ),
        "",
    ]
    for ticket in tickets:
        fp = str(ticket.get("fingerprint", ""))[:12]
        state = str(ticket.get("state", ""))
        source = str(ticket.get("source", ""))
        asset = ticket.get("candidate_asset")
        asset_str = str(asset) if asset else "—"
        pattern = str(ticket.get("pattern", "(no pattern)"))
        distinct_runs = ticket.get("distinct_runs", 0)
        lines += [
            f"## `{fp}` — {pattern[:80]}",
            "",
            f"- **state**: {state}  **source**: {source}  "
            f"**asset**: {asset_str}  **distinct runs**: {distinct_runs}",
            "",
            "**Evidence sample:**",
            _fmt_evidence(ticket),
            "",
        ]
    return "\n".join(lines)


def resolve_learnings(
    repo_root: Path,
    scope_files: Sequence[str],
    dest_dir: Path,
) -> Path | None:
    """Resolve and ALWAYS write ``context-bundle/learnings.md`` for a contract.

    Loads the ledger for ``repo_root``, selects relevant gate-passed tickets, and
    writes ``<dest_dir>/context-bundle/learnings.md`` — real content when tickets
    match, the ``_BLIND_MARKER`` when none do (or injection is disabled).  The
    file is written on EVERY path so the dispatch-contract-gate can treat its
    presence as proof injection ran.

    Returns the path when real tickets matched, ``None`` on a blind path (caller's
    ``matched`` count keys off this) — but the marker file is written either way.

    If ``AUTO_PILOT_DISABLE_LEARNINGS`` is set to ``1``, ``true``, ``yes``, or
    ``on`` (case-insensitive), injection is skipped (marker written, ``None``
    returned) — the no-inject arm for outcome-level A/B evals
    (``evals/cases/learnings-ab/``).  Any other value (including ``0``,
    ``false``, ``no``, ``off``, empty string, or unset) leaves injection ON so
    that setting ``=0`` to mean "keep enabled" is not misread as a disable.
    """
    bundle = dest_dir / "context-bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    learnings_path = bundle / "learnings.md"

    _disable = os.environ.get("AUTO_PILOT_DISABLE_LEARNINGS", "").strip().lower()
    if _disable in {"1", "true", "yes", "on"}:
        sys.stderr.write(
            "_learnings: injection disabled via AUTO_PILOT_DISABLE_LEARNINGS\n"
        )
        learnings_path.write_text(_BLIND_MARKER)
        return None
    ledger = ledger_dir(repo_root, None)
    tickets = select_tickets(ledger, scope_files)
    if not tickets:
        sys.stderr.write("_learnings: no relevant promotable tickets — ran learnings-blind\n")
        learnings_path.write_text(_BLIND_MARKER)
        return None

    learnings_path.write_text(render_learnings(tickets))
    return learnings_path
