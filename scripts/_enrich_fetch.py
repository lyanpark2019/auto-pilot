"""Live-fetch shaping seam for increment-2 Phase 2b enrichment.

The MCP I/O is an agent action (agents/enrichment-fetcher.md owns the real
network calls); this module owns the deterministic shaping and gate/persist
wiring behind an injectable Fetcher.  retrieved_date is always a
caller-supplied parameter — never generated here — so persist stays
byte-stable across re-runs on the same date.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, TypedDict

from _enrich_gate import canonical_sha
from _enrich_persist import persist


# ---------------------------------------------------------------------------
# Input types (raw MCP hit shape — no sha256; shape_hit computes it)
# ---------------------------------------------------------------------------


class RawCorroboration(TypedDict):
    """source_url and snippet from the MCP fetch result (no sha256 field)."""

    source_url: str
    snippet: str


class RawHit(TypedDict, total=False):
    """Minimal raw hit dict from a Fetcher.fetch() call.

    Required keys: claim, source_url, snippet.
    Optional: corroborations, repro_passed, notes, llm_judge.
    No sha256 — shape_hit computes it.
    """

    claim: str
    source_url: str
    snippet: str
    corroborations: list[RawCorroboration]
    repro_passed: bool | None
    notes: str
    llm_judge: dict[str, Any] | None


# ---------------------------------------------------------------------------
# Fetcher Protocol (MCP boundary)
# ---------------------------------------------------------------------------


class Fetcher(Protocol):
    """Injectable fetch interface; the real implementation lives in the agent."""

    def fetch(self, query: str, tier: str) -> list[RawHit]:
        """Return raw hits for the given query and source tier."""
        ...


# ---------------------------------------------------------------------------
# Shaping
# ---------------------------------------------------------------------------


def shape_hit(
    raw_hit: RawHit,
    source_tier: str,
    retrieved_date: str,
) -> dict[str, Any]:
    """Build a schema-valid enrichment-evidence candidate from a raw MCP hit.

    Computes sha256 from the snippet; computes per-corroboration sha256 the
    same way.  Does NOT gate or filter — that is _enrich_gate.evaluate's role.
    Pure: no network, no side effects, no date generation.
    """
    snippet: str = str(raw_hit.get("snippet", ""))
    candidate: dict[str, Any] = {
        "claim": str(raw_hit.get("claim", "")),
        "source_tier": source_tier,
        "source_url": str(raw_hit.get("source_url", "")),
        "retrieved_date": retrieved_date,
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
    }

    raw_corrs: list[Any] = raw_hit.get("corroborations") or []
    if raw_corrs:
        shaped_corrs: list[dict[str, Any]] = []
        for raw_corr in raw_corrs:
            corr_snippet: str = str(raw_corr.get("snippet", ""))
            shaped_corrs.append({
                "source_url": str(raw_corr.get("source_url", "")),
                "snippet": corr_snippet,
                "sha256": canonical_sha(corr_snippet),
            })
        candidate["corroborations"] = shaped_corrs

    repro_passed = raw_hit.get("repro_passed")
    if repro_passed is not None:
        candidate["repro_passed"] = repro_passed

    notes = raw_hit.get("notes")
    if notes is not None:
        candidate["notes"] = str(notes)

    llm_judge = raw_hit.get("llm_judge")
    if llm_judge is not None:
        candidate["llm_judge"] = llm_judge

    return candidate


# ---------------------------------------------------------------------------
# Fetch-and-persist pipeline
# ---------------------------------------------------------------------------


def fetch_and_persist(
    fetcher: Fetcher,
    query: str,
    vault: Path,
    *,
    retrieved_date: str,
    tiers: tuple[str, ...] = ("official", "community"),
    dry_run: bool = False,
) -> dict[str, int]:
    """Fetch hits for each tier, shape them, then gate-and-persist.

    Returns the same counts dict as _enrich_persist.persist:
    {admitted, rejected, written, unchanged}.
    """
    candidates: list[dict[str, Any]] = []
    for tier in tiers:
        raw_hits = fetcher.fetch(query, tier)
        for raw_hit in raw_hits:
            candidates.append(shape_hit(raw_hit, tier, retrieved_date))

    return persist(candidates, vault, dry_run=dry_run)
