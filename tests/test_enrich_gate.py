"""Tests for scripts/_enrich_gate.py — deterministic enrichment gate.

All candidate dicts are built with correctly-computed sha256 values via
canonical_sha() so the tests exercise the REAL evaluate() logic, not stubs.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _enrich_gate import canonical_sha, evaluate  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _official_candidate(**overrides: object) -> dict:
    """Minimal valid official-tier candidate; override any field via kwargs."""
    snippet = "The correct answer is 42."
    base: dict = {
        "claim": "Answer to everything",
        "source_tier": "official",
        "source_url": "https://docs.example.com/answer",
        "retrieved_date": "2026-06-14",
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
    }
    base.update(overrides)
    return base


def _community_candidate(**overrides: object) -> dict:
    """Minimal community-tier candidate (no corroborations by default)."""
    snippet = "Community tip: use frobnicate() instead."
    base: dict = {
        "claim": "Use frobnicate",
        "source_tier": "community",
        "source_url": "https://reddit.com/r/python/1234",
        "retrieved_date": "2026-06-14",
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
        "corroborations": [],
    }
    base.update(overrides)
    return base


def _corroboration(url: str, snippet: str) -> dict:
    return {
        "source_url": url,
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
    }


# ---------------------------------------------------------------------------
# Official tier
# ---------------------------------------------------------------------------


def test_official_complete_admits() -> None:
    result = evaluate(_official_candidate())
    assert result["verdict"] == "admit"
    assert result["evidence_complete"] is True
    assert result["source_tier"] == "official"


def test_official_empty_snippet_rejects() -> None:
    cand = _official_candidate(snippet="", sha256=canonical_sha(""))
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    # schema minLength 1 fires first — reason is "schema-invalid: '' should be non-empty"
    assert len(result["reasons"]) >= 1


def test_official_sha_mismatch_rejects() -> None:
    cand = _official_candidate(sha256="a" * 64)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("sha256 mismatch" in r for r in result["reasons"])


def test_official_bad_retrieved_date_rejects() -> None:
    cand = _official_candidate(retrieved_date="not-a-date")
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("retrieved_date" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# Community tier — corroboration count
# ---------------------------------------------------------------------------


def test_community_zero_corroborations_no_repro_rejects() -> None:
    result = evaluate(_community_candidate(repro_passed=None))
    assert result["verdict"] == "reject"
    assert any("community tier" in r for r in result["reasons"])


def test_community_one_corroboration_rejects() -> None:
    corrs = [
        _corroboration("https://stackoverflow.com/q/1", "Stack tip for frobnicate"),
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("community tier" in r for r in result["reasons"])


def test_community_two_distinct_corroborations_admits() -> None:
    corrs = [
        _corroboration("https://stackoverflow.com/q/1", "Stack tip for frobnicate"),
        _corroboration("https://dev.to/article/2", "Dev.to tip for frobnicate"),
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "admit"
    assert result["evidence_complete"] is True


def test_community_two_same_host_rejects() -> None:
    corrs = [
        _corroboration("https://stackoverflow.com/q/1", "Stack tip A"),
        _corroboration("https://stackoverflow.com/q/2", "Stack tip B"),
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("not independent" in r for r in result["reasons"])


def test_community_repro_passed_admits() -> None:
    cand = _community_candidate(repro_passed=True, corroborations=[])
    result = evaluate(cand)
    assert result["verdict"] == "admit"
    assert result["evidence_complete"] is True


def test_community_bad_sha_corroboration_does_not_count() -> None:
    """1 bad-sha corroboration + 1 good → only 1 valid, should reject."""
    good_corr = _corroboration("https://stackoverflow.com/q/1", "Good corr")
    bad_corr = {
        "source_url": "https://dev.to/article/2",
        "snippet": "Bad corr snippet",
        "sha256": "b" * 64,  # wrong sha
    }
    cand = _community_candidate(corroborations=[bad_corr, good_corr])
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    # bad sha should be noted
    assert any("sha256 mismatch" in r for r in result["reasons"])
    # only 1 valid corroboration → not enough
    assert any("community tier" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# Advisory LLM judge — must NOT override verdict
# ---------------------------------------------------------------------------


def test_advisory_judge_reject_does_not_flip_admit() -> None:
    """Official + complete + llm_judge reject → still ADMITs; judge is advisory."""
    cand = _official_candidate(
        llm_judge={"verdict": "reject", "reason": "I disagree"}
    )
    result = evaluate(cand)
    assert result["verdict"] == "admit"
    assert result["advisory_judge"] == {"verdict": "reject", "reason": "I disagree"}
    assert any("advisory only" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# Schema-invalid input — must never raise
# ---------------------------------------------------------------------------


def test_schema_invalid_missing_claim_rejects_and_does_not_raise() -> None:
    bad: dict = {
        # "claim" is missing
        "source_tier": "official",
        "source_url": "https://docs.example.com/answer",
        "retrieved_date": "2026-06-14",
        "snippet": "Some text",
        "sha256": canonical_sha("Some text"),
    }
    result = evaluate(bad)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("schema-invalid" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# Non-dict input — "never raises" boundary (Fix 1)
# ---------------------------------------------------------------------------


import pytest  # noqa: E402


@pytest.mark.parametrize("bad_input", [None, [], "x", 42, 3.14])
def test_non_dict_input_rejects_and_does_not_raise(bad_input: object) -> None:
    """evaluate() must return a reject dict for any non-dict input — never raise."""
    result = evaluate(bad_input)  # type: ignore[arg-type]
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("not an object" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# Whitespace-only snippet — gate hole closed (Fix 2)
# ---------------------------------------------------------------------------


def test_official_whitespace_snippet_rejects() -> None:
    """Whitespace-only snippet must be rejected (evidence_complete=False).

    sha256 is computed from the raw whitespace snippet so the test proves it
    is the content check (not a sha mismatch) that drives the rejection.
    """
    snippet = "   "
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("visible content" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# ISO date edge cases
# ---------------------------------------------------------------------------


def test_official_datetime_string_admits() -> None:
    """ISO date-time in retrieved_date is accepted."""
    cand = _official_candidate(retrieved_date="2026-06-14T12:34:56+00:00")
    result = evaluate(cand)
    assert result["verdict"] == "admit"


def test_official_z_suffix_datetime_admits() -> None:
    """Trailing Z in date-time is normalised and accepted."""
    cand = _official_candidate(retrieved_date="2026-06-14T12:34:56Z")
    result = evaluate(cand)
    assert result["verdict"] == "admit"


# ---------------------------------------------------------------------------
# Bypass fixes — RED-proven cases (P0 + P1a/b/c/d + positive control)
# ---------------------------------------------------------------------------


def test_official_zero_width_space_snippet_rejects() -> None:
    """U+200B zero-width space snippet must be rejected (P0 fix).

    sha256 matches the raw snippet content — proves it is _has_visible_content
    that drives the rejection, not a sha mismatch.
    """
    zwsp = "​"
    cand = _official_candidate(snippet=zwsp, sha256=canonical_sha(zwsp))
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("visible content" in r for r in result["reasons"])


def test_community_whitespace_corroboration_does_not_count() -> None:
    """A corroboration with a whitespace-only snippet must not count (P1a fix).

    1 real corroboration + 1 whitespace corroboration → only 1 valid → reject.
    sha256 values match the raw snippets so it is the content check, not sha,
    that rejects the blank corroboration.
    """
    blank_snip = "   "
    corrs = [
        _corroboration("https://stackoverflow.com/q/1", "Real first corroboration"),
        {
            "source_url": "https://dev.to/article/2",
            "snippet": blank_snip,
            "sha256": canonical_sha(blank_snip),
        },
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("visible content" in r for r in result["reasons"])
    assert any("community tier" in r for r in result["reasons"])


def test_community_zero_width_corroboration_does_not_count() -> None:
    """A corroboration with a U+200B-only snippet must not count (P1b fix).

    1 real corroboration + 1 zero-width-space corroboration → only 1 valid → reject.
    """
    zwsp = "​"
    corrs = [
        _corroboration("https://stackoverflow.com/q/1", "Real first corroboration"),
        {
            "source_url": "https://dev.to/article/2",
            "snippet": zwsp,
            "sha256": canonical_sha(zwsp),
        },
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("visible content" in r for r in result["reasons"])
    assert any("community tier" in r for r in result["reasons"])


def test_community_hostless_urn_corroborations_reject() -> None:
    """Two sha-valid corroborations with urn: (no host) URLs must not count (P1c fix).

    A hostless URL is never an independent source.
    """
    snip_a = "Content at urn corr a"
    snip_b = "Content at urn corr b"
    corrs = [
        {"source_url": "urn:corr:a", "snippet": snip_a, "sha256": canonical_sha(snip_a)},
        {"source_url": "urn:corr:b", "snippet": snip_b, "sha256": canonical_sha(snip_b)},
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("no host" in r for r in result["reasons"])
    assert any("community tier" in r for r in result["reasons"])


def test_community_trailing_dot_host_collision_rejects() -> None:
    """example.com and example.com. canonicalize to the same host (P1d fix).

    Two corroborations from the same canonical host → only 1 distinct → reject.
    """
    snip_x = "Content from example.com"
    snip_y = "Content from example.com with trailing dot"
    corrs = [
        _corroboration("https://example.com/x", snip_x),
        _corroboration("https://example.com./y", snip_y),
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("not independent" in r for r in result["reasons"])
    assert any("community tier" in r for r in result["reasons"])


def test_community_two_genuinely_distinct_hosts_admits() -> None:
    """Positive control: 2 corroborations from genuinely distinct hosts admit (P1d fix).

    Ensures the canonicalization doesn't over-reject valid cases.
    """
    corrs = [
        _corroboration("https://a.com/page", "Content from a.com"),
        _corroboration("https://b.com/page", "Content from b.com"),
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "admit"
    assert result["evidence_complete"] is True


# ---------------------------------------------------------------------------
# Whitespace-in-URL gate (Fix 1)
# ---------------------------------------------------------------------------


def test_official_newline_in_source_url_rejects() -> None:
    """Official candidate with a newline in source_url must be rejected.

    sha256 matches the snippet — rejection is driven by the whitespace URL check,
    not a sha mismatch.  A newline in source_url renders as malformed YAML frontmatter.
    """
    snippet = "The correct answer is 42."
    cand = _official_candidate(
        source_url="https://x.io/p\ninjected",
        sha256=canonical_sha(snippet),
    )
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("source_url contains whitespace" in r for r in result["reasons"])


def test_community_whitespace_url_corroboration_does_not_count() -> None:
    """A corroboration whose source_url contains whitespace must not count.

    1 valid corroboration + 1 tab-URL corroboration → only 1 valid → reject.
    sha256 matches both corroboration snippets so the rejection is URL-whitespace, not sha.
    """
    corrs = [
        _corroboration("https://stackoverflow.com/q/1", "Good first corroboration"),
        {
            "source_url": "https://dev.to/p\tinjected",
            "snippet": "Corr with whitespace url",
            "sha256": canonical_sha("Corr with whitespace url"),
        },
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("source_url contains whitespace" in r for r in result["reasons"])
    assert any("community tier" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# Phase 2b residuals — blank-codepoint + IDN/punycode + trailing-dot (CLOSED)
# ---------------------------------------------------------------------------


def test_official_hangul_filler_snippet_rejects() -> None:
    """U+1160 HANGUL JUNGSEONG FILLER (Lo) must be rejected — renders blank.

    sha256 matches the raw snippet so rejection is driven by _has_visible_content,
    not a sha mismatch. NFKC folds U+3164 → U+1160, still in _BLANK_RENDER_CODEPOINTS.
    """
    snippet = "ㅤ"  # HANGUL FILLER (NFKC → U+1160 HANGUL JUNGSEONG FILLER)
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("visible content" in r for r in result["reasons"])


def test_official_halfwidth_hangul_filler_snippet_rejects() -> None:
    """U+FFA0 HALFWIDTH HANGUL FILLER NFKC-folds to U+1160 — must reject."""
    snippet = "ﾠ"  # HALFWIDTH HANGUL FILLER (NFKC → U+1160)
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("visible content" in r for r in result["reasons"])


def test_official_braille_blank_snippet_rejects() -> None:
    """U+2800 BRAILLE PATTERN BLANK (So, NFKC-stable) must be rejected — renders blank."""
    snippet = "⠀"  # BRAILLE PATTERN BLANK
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("visible content" in r for r in result["reasons"])


def test_official_combining_mark_only_snippet_rejects() -> None:
    """A snippet of only combining marks (Mn) has no base — must be rejected."""
    snippet = "́́"  # two COMBINING ACUTE ACCENT (Mn)
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("visible content" in r for r in result["reasons"])


def test_community_hangul_filler_corroboration_does_not_count() -> None:
    """A corroboration with a Hangul-filler snippet must not count.

    1 valid distinct-host corroboration + 1 with snippet=U+3164 (sha-valid,
    distinct host) → only 1 valid → reject.  Asserts both visible-content
    and community-tier reasons are present.
    """
    filler_snip = "ㅤ"
    corrs = [
        _corroboration("https://stackoverflow.com/q/1", "Real corroboration text"),
        {
            "source_url": "https://dev.to/article/blank",
            "snippet": filler_snip,
            "sha256": canonical_sha(filler_snip),
        },
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("visible content" in r for r in result["reasons"])
    assert any("community tier" in r for r in result["reasons"])


def test_community_punycode_vs_unicode_idn_same_host_rejects() -> None:
    """Unicode IDN and its xn-- punycode form canonicalize to the same host.

    Two corroborations: one on the Unicode IDN host, one on the xn-- form.
    Both IDNA-encode to the same punycode → 1 distinct host → reject.
    """
    snip_a = "Content from unicode IDN host"
    snip_b = "Content from punycode host"
    corrs = [
        _corroboration("https://例え.テスト/a", snip_a),
        _corroboration("https://xn--r8jz45g.xn--zckzah/b", snip_b),
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("not independent" in r for r in result["reasons"])


def test_community_multi_trailing_dot_host_collision_rejects() -> None:
    """Hosts example.com and example.com.. both strip to example.com → same host.

    Two corroborations collapsing to one canonical host → reject.
    """
    snip_x = "Content from example.com"
    snip_y = "Content from example.com with extra dots"
    corrs = [
        _corroboration("https://example.com/x", snip_x),
        _corroboration("https://example.com../y", snip_y),
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert any("not independent" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# Positive-control tests — guards against over-rejection of real script
# ---------------------------------------------------------------------------


def test_official_cjk_snippet_admits() -> None:
    """Korean CJK text must be admitted — not a blank-render codepoint."""
    snippet = "가나다 한국어 문서"
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "admit"


def test_official_thai_snippet_admits() -> None:
    """Thai script must be admitted."""
    snippet = "ข้อความภาษาไทย"
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "admit"


def test_official_devanagari_snippet_admits() -> None:
    """Devanagari script must be admitted."""
    snippet = "नमस्ते"
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "admit"


def test_community_genuinely_distinct_idn_hosts_admit() -> None:
    """Two corroborations on genuinely different IDN hosts must be admitted.

    xn--r8jz45g.xn--zckzah (例え.テスト) and xn--e1afmkfd.xn--p1ai (пример.рф)
    are different punycode domains — they must count as 2 distinct hosts.
    """
    snip_a = "Content from japanese IDN host"
    snip_b = "Content from russian IDN host"
    corrs = [
        _corroboration("https://例え.テスト/a", snip_a),
        _corroboration("https://пример.рф/b", snip_b),
    ]
    cand = _community_candidate(corroborations=corrs)
    result = evaluate(cand)
    assert result["verdict"] == "admit"
    assert result["evidence_complete"] is True


def test_official_braille_text_admits() -> None:
    """Real Braille codepoints (not U+2800 blank) must be admitted."""
    snippet = "⠁⠂⠃"  # ⠁⠂⠃ — actual Braille patterns with dots
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "admit"


# ---------------------------------------------------------------------------
# Cn/Co/Cs blank-snippet bypass — closed (FIX 1)
# ---------------------------------------------------------------------------


def test_official_private_use_snippet_rejects() -> None:
    """A snippet of only Private-Use Area codepoints (Co, U+E000) must be rejected.

    PUA codepoints render as blank/tofu — no glyph in standard fonts.  sha256
    matches the raw snippet so the rejection is driven by _has_visible_content
    (Cn/Co/Cs now in the non-rendering category block), not a sha mismatch.
    """
    snippet = ""  # U+E000 PRIVATE USE AREA (Co)
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("visible content" in r for r in result["reasons"])


def test_official_unassigned_codepoint_snippet_rejects() -> None:
    """A snippet of only unassigned codepoints (Cn) must be rejected.

    U+0378 is an unassigned codepoint (Cn) — no glyph, renders blank/tofu.
    sha256 matches the raw snippet so it is _has_visible_content that rejects.
    """
    snippet = "͸"  # U+0378 — unassigned (Cn)
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "reject"
    assert result["evidence_complete"] is False
    assert any("visible content" in r for r in result["reasons"])


def test_official_mixed_text_with_pua_admits() -> None:
    """A snippet with real letters AND a Private-Use codepoint must be admitted.

    Only ALL-invisible snippets should reject; one real letter is sufficient to
    pass _has_visible_content even when PUA characters are also present.
    """
    snippet = "real text  here"  # real letters + one PUA
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "admit"
    assert result["evidence_complete"] is True


def test_official_base_plus_combining_mark_admits() -> None:
    """A base letter with a combining mark (Mn) must be admitted.

    'é' = 'e' (Ll) + COMBINING ACUTE ACCENT (U+0301, Mn).  The base 'e' is
    visible; only lone combining marks (no base) should be rejected.
    """
    snippet = "é"  # 'e' + COMBINING ACUTE ACCENT = é
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "admit"
    assert result["evidence_complete"] is True
