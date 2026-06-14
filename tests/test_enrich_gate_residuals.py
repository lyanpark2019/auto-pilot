"""Phase-2b residual-hardening tests (NFKC/IDNA/blank-codepoint) split from
test_enrich_gate.py to satisfy the ≤500-line module-size gate."""
from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _enrich_gate import canonical_sha, evaluate  # noqa: E402
from test_enrich_gate import (  # noqa: E402
    _community_candidate,
    _corroboration,
    _official_candidate,
)


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
    snippet = "é"  # 'e' + COMBINING ACUTE ACCENT = é
    cand = _official_candidate(snippet=snippet, sha256=canonical_sha(snippet))
    result = evaluate(cand)
    assert result["verdict"] == "admit"
    assert result["evidence_complete"] is True
