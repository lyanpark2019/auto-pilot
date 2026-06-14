"""Tests for scripts/_enrich_fetch.py — live-fetch shaping seam.

All tests are deterministic: network calls are replaced by FakeFetcher.
The fixed retrieved_date "2026-06-14" is used throughout so sha-based
byte-stability can be verified without clock dependencies.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable when running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _enrich_fetch  # noqa: E402 (needed after sys.path insert)
import inspect  # noqa: E402

from _enrich_gate import canonical_sha, evaluate  # noqa: E402
from _enrich_fetch import fetch_and_persist, shape_hit  # noqa: E402

RETRIEVED = "2026-06-14"


# ---------------------------------------------------------------------------
# FakeFetcher
# ---------------------------------------------------------------------------


class FakeFetcher:
    """Deterministic stand-in for the real MCP fetcher."""

    def __init__(self, hits_by_tier: dict[str, list[dict]]) -> None:
        self._hits = hits_by_tier

    def fetch(self, query: str, tier: str) -> list[dict]:
        return self._hits.get(tier, [])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _official_hit(
    snippet: str = "Official snippet content.",
    url: str = "https://docs.example.com/api/v1",
    claim: str = "The API works this way.",
) -> dict:
    return {"claim": claim, "source_url": url, "snippet": snippet}


def _community_hit(
    snippet: str = "Community tip content.",
    url: str = "https://reddit.com/r/python/12345",
    claim: str = "Community claim.",
    corroborations: list[dict] | None = None,
    repro_passed: bool | None = None,
) -> dict:
    hit: dict = {"claim": claim, "source_url": url, "snippet": snippet}
    if corroborations is not None:
        hit["corroborations"] = corroborations
    if repro_passed is not None:
        hit["repro_passed"] = repro_passed
    return hit


def _corroboration(url: str, snippet: str) -> dict:
    return {"source_url": url, "snippet": snippet}


# ---------------------------------------------------------------------------
# 1. One official hit → admitted + written, exactly one enrichment page
# ---------------------------------------------------------------------------


def test_official_hit_one_byte_stable_page(tmp_path: Path) -> None:
    fetcher = FakeFetcher({"official": [_official_hit()]})
    counts = fetch_and_persist(fetcher, "query", tmp_path, retrieved_date=RETRIEVED)
    assert counts["admitted"] == 1
    assert counts["written"] == 1
    pages = list((tmp_path / "enrichment").glob("enrich-*.md"))
    assert len(pages) == 1


# ---------------------------------------------------------------------------
# 2. Two runs on the same date → second run: unchanged==1, written==0, bytes identical
# ---------------------------------------------------------------------------


def test_official_page_byte_stable_rerun(tmp_path: Path) -> None:
    fetcher = FakeFetcher({"official": [_official_hit(snippet="Stable snippet.")]})
    counts1 = fetch_and_persist(fetcher, "q", tmp_path, retrieved_date=RETRIEVED)
    assert counts1["written"] == 1

    page = list((tmp_path / "enrichment").glob("enrich-*.md"))[0]
    bytes_run1 = page.read_bytes()

    counts2 = fetch_and_persist(fetcher, "q", tmp_path, retrieved_date=RETRIEVED)
    assert counts2["unchanged"] == 1
    assert counts2["written"] == 0

    assert page.read_bytes() == bytes_run1


# ---------------------------------------------------------------------------
# 3. Community single source (0 corroborations, no repro) → rejected, zero pages
# ---------------------------------------------------------------------------


def test_community_single_source_no_page(tmp_path: Path) -> None:
    fetcher = FakeFetcher({"community": [_community_hit()]})
    counts = fetch_and_persist(fetcher, "q", tmp_path, retrieved_date=RETRIEVED)
    assert counts["admitted"] == 0
    assert counts["rejected"] == 1
    enrichment_dir = tmp_path / "enrichment"
    pages = list(enrichment_dir.glob("*.md")) if enrichment_dir.exists() else []
    assert pages == []


# ---------------------------------------------------------------------------
# 4. Community hit + 2 corroborations on distinct hosts → admitted, one page
# ---------------------------------------------------------------------------


def test_community_two_distinct_hosts_one_page(tmp_path: Path) -> None:
    hit = _community_hit(
        corroborations=[
            _corroboration("https://forum.a.io/thread/1", "Alpha corroboration text."),
            _corroboration("https://blog.b.com/posts/1", "Beta corroboration text."),
        ]
    )
    fetcher = FakeFetcher({"community": [hit]})
    counts = fetch_and_persist(fetcher, "q", tmp_path, retrieved_date=RETRIEVED)
    assert counts["admitted"] == 1
    pages = list((tmp_path / "enrichment").glob("enrich-*.md"))
    assert len(pages) == 1


# ---------------------------------------------------------------------------
# 5. Community hit, repro_passed True, 0 corroborations → admitted, one page
# ---------------------------------------------------------------------------


def test_community_repro_passed_one_page(tmp_path: Path) -> None:
    hit = _community_hit(repro_passed=True)
    fetcher = FakeFetcher({"community": [hit]})
    counts = fetch_and_persist(fetcher, "q", tmp_path, retrieved_date=RETRIEVED)
    assert counts["admitted"] == 1
    pages = list((tmp_path / "enrichment").glob("enrich-*.md"))
    assert len(pages) == 1


# ---------------------------------------------------------------------------
# 6. Community hit + 2 corroborations on same exact hostname → rejected, zero pages
# Note: the gate uses plain hostname comparison (no eTLD+1); two URLs on the
# same hostname (e.g. both reddit.com/r/python/) are correctly rejected.
# The www. vs old. subdomain residual is a deferred Phase-1 known limitation
# documented in docs/specs/2026-06-14-enrich-gate-increment2.md.
# ---------------------------------------------------------------------------


def test_community_two_same_host_no_page(tmp_path: Path) -> None:
    hit = _community_hit(
        corroborations=[
            _corroboration("https://reddit.com/r/python/1", "First reddit post."),
            _corroboration("https://reddit.com/r/python/2", "Second reddit post."),
        ]
    )
    fetcher = FakeFetcher({"community": [hit]})
    counts = fetch_and_persist(fetcher, "q", tmp_path, retrieved_date=RETRIEVED)
    assert counts["admitted"] == 0
    assert counts["rejected"] == 1
    enrichment_dir = tmp_path / "enrichment"
    pages = list(enrichment_dir.glob("*.md")) if enrichment_dir.exists() else []
    assert pages == []


# ---------------------------------------------------------------------------
# 7. Mixed tiers: official admit + community single-source reject → admitted==1, rejected==1
# ---------------------------------------------------------------------------


def test_mixed_tiers_official_admit_community_single_reject(tmp_path: Path) -> None:
    fetcher = FakeFetcher({
        "official": [_official_hit()],
        "community": [_community_hit()],
    })
    counts = fetch_and_persist(fetcher, "q", tmp_path, retrieved_date=RETRIEVED)
    assert counts["admitted"] == 1
    assert counts["rejected"] == 1
    pages = list((tmp_path / "enrichment").glob("enrich-*.md"))
    assert len(pages) == 1


# ---------------------------------------------------------------------------
# shape_hit unit tests (no persist)
# ---------------------------------------------------------------------------


# 8. sha256 in shaped output matches canonical_sha(snippet)
def test_shape_hit_sha256_matches_canonical() -> None:
    snippet = "Test snippet for sha."
    raw = _official_hit(snippet=snippet)
    shaped = shape_hit(raw, "official", RETRIEVED)
    assert shaped["sha256"] == canonical_sha(snippet)


# 9. shaped output fed to evaluate → official complete → verdict "admit"
def test_shape_hit_output_is_schema_valid() -> None:
    raw = _official_hit(
        snippet="Valid official snippet.",
        url="https://docs.lib.io/ref",
        claim="This is the claim.",
    )
    shaped = shape_hit(raw, "official", RETRIEVED)
    result = evaluate(shaped)
    assert result["verdict"] == "admit", f"expected admit, reasons: {result['reasons']}"


# 10. each corroboration sha matches canonical_sha(its snippet); raw input had no sha
def test_shape_hit_corroboration_shas_computed() -> None:
    corr1_snip = "First corroboration snippet."
    corr2_snip = "Second corroboration snippet."
    raw = _community_hit(
        corroborations=[
            {"source_url": "https://a.io/1", "snippet": corr1_snip},
            {"source_url": "https://b.com/2", "snippet": corr2_snip},
        ]
    )
    shaped = shape_hit(raw, "community", RETRIEVED)
    corrs = shaped["corroborations"]
    assert corrs[0]["sha256"] == canonical_sha(corr1_snip)
    assert corrs[1]["sha256"] == canonical_sha(corr2_snip)
    # raw input had no sha256 on corroborations
    assert "sha256" not in raw.get("corroborations", [{}])[0]


# 11. output uses supplied retrieved_date; module source has no now()/today()
def test_shape_hit_uses_supplied_retrieved_date() -> None:
    raw = _official_hit()
    shaped = shape_hit(raw, "official", RETRIEVED)
    assert shaped["retrieved_date"] == RETRIEVED

    src = inspect.getsource(_enrich_fetch)
    assert "now()" not in src, "module must not call now()"
    assert "today()" not in src, "module must not call today()"


# 12. optional fields llm_judge and repro_passed are preserved
def test_shape_hit_passes_through_llm_judge_and_repro() -> None:
    llm_judge = {"verdict": "admit", "reason": "looks good"}
    raw = _community_hit(repro_passed=True)
    raw["llm_judge"] = llm_judge
    shaped = shape_hit(raw, "community", RETRIEVED)
    assert shaped.get("repro_passed") is True
    assert shaped.get("llm_judge") == llm_judge


# 13. Official hit whose snippet is a blank codepoint (U+3164 Hangul filler) → gated out
def test_official_blank_codepoint_snippet_gated_out(tmp_path: Path) -> None:
    fetcher = FakeFetcher({"official": [_official_hit(snippet="ㅤ")]})
    counts = fetch_and_persist(fetcher, "q", tmp_path, retrieved_date=RETRIEVED)
    assert counts["admitted"] == 0
    assert counts["rejected"] == 1
    assert list(tmp_path.glob("enrichment/enrich-*.md")) == []


# 14. dry_run=True → no .md files created
def test_fetch_and_persist_dry_run_no_writes(tmp_path: Path) -> None:
    fetcher = FakeFetcher({"official": [_official_hit()]})
    counts = fetch_and_persist(fetcher, "q", tmp_path, retrieved_date=RETRIEVED, dry_run=True)
    assert counts["admitted"] == 1
    assert counts["written"] == 1  # counted but not written to disk
    enrichment_dir = tmp_path / "enrichment"
    pages = list(enrichment_dir.glob("*.md")) if enrichment_dir.exists() else []
    assert pages == [], "dry_run must not create any files"
