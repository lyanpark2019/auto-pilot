"""Tests for scripts/measure_enrich_precision.py — gate-precision instrument.

Uses real candidate fixture builders (mirrored from test_enrich_persist.py) and
exercises the real measure() — no mocking of gate internals.  Honest results:
0%/100%/mixed admit rates and the empty-list zero-division guard.
"""
from __future__ import annotations

import copy
import inspect
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import measure_enrich_precision as mep  # noqa: E402
from _enrich_gate import canonical_sha  # noqa: E402


# ---------------------------------------------------------------------------
# Candidate fixture builders (mirrored from test_enrich_persist.py)
# ---------------------------------------------------------------------------


def _official(snippet: str = "Correct answer is 42.", **overrides: object) -> dict:
    base: dict = {
        "claim": "The answer",
        "source_tier": "official",
        "source_url": "https://docs.example.com/answer",
        "retrieved_date": "2026-06-14",
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
    }
    base.update(overrides)
    return base


def _community_two_corr(
    snippet: str = "Community tip: frobnicate().",
    corr1_url: str = "https://forum.a.io/thread/1",
    corr2_url: str = "https://blog.b.com/posts/1",
) -> dict:
    corr1_snip = "Corroboration alpha."
    corr2_snip = "Corroboration beta."
    return {
        "claim": "Use frobnicate",
        "source_tier": "community",
        "source_url": "https://reddit.com/r/python/9999",
        "retrieved_date": "2026-06-14",
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
        "corroborations": [
            {
                "source_url": corr1_url,
                "snippet": corr1_snip,
                "sha256": canonical_sha(corr1_snip),
            },
            {
                "source_url": corr2_url,
                "snippet": corr2_snip,
                "sha256": canonical_sha(corr2_snip),
            },
        ],
    }


def _community_single(snippet: str = "Community tip alone.") -> dict:
    corr_snip = "Single corroboration."
    return {
        "claim": "Single source community",
        "source_tier": "community",
        "source_url": "https://reddit.com/r/python/0001",
        "retrieved_date": "2026-06-14",
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
        "corroborations": [
            {
                "source_url": "https://forum.only.one/thread",
                "snippet": corr_snip,
                "sha256": canonical_sha(corr_snip),
            }
        ],
    }


# ---------------------------------------------------------------------------
# 1. All official → 100% admit rate
# ---------------------------------------------------------------------------


def test_all_official_admitted() -> None:
    """N official candidates → all admitted, admit_rate_pct == 100.0."""
    N = 3
    candidates = [_official(snippet=f"Fact {i}.") for i in range(N)]
    result = mep.measure(candidates)

    assert result["total"] == N
    assert result["admitted"] == N
    assert result["rejected"] == 0
    assert result["admit_rate_pct"] == 100.0
    assert result["by_tier"]["official"]["admitted"] == N
    assert result["by_tier"]["official"]["rejected"] == 0


# ---------------------------------------------------------------------------
# 2. All community_single → 0% admit rate, reason histogram non-empty
# ---------------------------------------------------------------------------


def test_all_community_single_rejected() -> None:
    """N community-single candidates → all rejected, reason_histogram non-empty."""
    N = 2
    candidates = [_community_single(snippet=f"Tip {i}.") for i in range(N)]
    result = mep.measure(candidates)

    assert result["total"] == N
    assert result["admitted"] == 0
    assert result["rejected"] == N
    assert result["admit_rate_pct"] == 0.0
    # The single-corroboration rejection reason must appear
    assert result["reason_histogram"], "reason_histogram must be non-empty"
    found_community_reason = any(
        "community tier" in r or "corroboration" in r
        for r in result["reason_histogram"]
    )
    assert found_community_reason, (
        f"expected community-under-corroboration reason in histogram, got: "
        f"{list(result['reason_histogram'])}"
    )


# ---------------------------------------------------------------------------
# 3. Mixed batch — correct counts and by_tier split
# ---------------------------------------------------------------------------


def test_mixed_batch_counts_and_by_tier() -> None:
    """official + community_two_corr + community_single → correct split."""
    official_c = _official(snippet="Official fact.")
    community_ok = _community_two_corr(snippet="Community ok.")
    community_bad = _community_single(snippet="Community bad.")

    result = mep.measure([official_c, community_ok, community_bad])

    assert result["total"] == 3
    assert result["admitted"] == 2  # official + community_two_corr
    assert result["rejected"] == 1  # community_single
    # by_tier split
    assert result["by_tier"]["official"]["admitted"] == 1
    assert result["by_tier"]["official"]["rejected"] == 0
    assert result["by_tier"]["community"]["admitted"] == 1
    assert result["by_tier"]["community"]["rejected"] == 1
    # community_single reason present
    assert result["reason_histogram"], "expected non-empty histogram"


# ---------------------------------------------------------------------------
# 4. Empty list → zeros, no ZeroDivisionError
# ---------------------------------------------------------------------------


def test_empty_list_all_zeros() -> None:
    """measure([]) must return all-zero counts, no ZeroDivisionError."""
    result = mep.measure([])

    assert result["total"] == 0
    assert result["admitted"] == 0
    assert result["rejected"] == 0
    assert result["admit_rate_pct"] == 0.0
    assert result["evidence_complete_pct"] == 0.0
    assert result["reason_histogram"] == {}
    assert result["advisory_judge_disagreements"] == 0
    assert result["advisory_judge_abstains"] == 0


# ---------------------------------------------------------------------------
# 5. evidence_complete_pct correct on known batch
# ---------------------------------------------------------------------------


def test_evidence_complete_pct() -> None:
    """Official candidates are evidence-complete; community-single is too (has content)."""
    # Official: evidence_complete = True (snippet + url + date + valid sha)
    # community_single: evidence_complete = True (same fields valid)
    # We test by mixing one candidate with forced sha mismatch (evidence_complete=False)
    good = _official(snippet="Good fact.")
    bad_sha = _official(snippet="Tampered.", sha256="0" * 64)  # sha mismatch → incomplete

    result = mep.measure([good, bad_sha])

    assert result["total"] == 2
    # good: evidence_complete=True; bad_sha: evidence_complete=False
    assert result["evidence_complete_pct"] == 50.0


# ---------------------------------------------------------------------------
# 6. advisory_judge_disagreements — disagreement counted, None judge not counted
# ---------------------------------------------------------------------------


def test_advisory_judge_disagreements() -> None:
    """Candidate with llm_judge verdict disagreeing with gate → counted."""
    # Official candidate will be admitted; give it an llm_judge that says reject
    # Schema: llm_judge.{verdict, reason} with additionalProperties: false
    c_disagree = _official(snippet="Disagreement test.")
    c_disagree["llm_judge"] = {"verdict": "reject", "reason": "test advisory"}

    # community_single will be rejected; give it llm_judge that says admit (disagree)
    c_single = _community_single(snippet="Advisory disagree single.")
    c_single["llm_judge"] = {"verdict": "admit", "reason": "advisory says yes"}

    # official with no llm_judge — should not be counted
    c_no_judge = _official(snippet="No judge here.")

    result = mep.measure([c_disagree, c_single, c_no_judge])

    # Both c_disagree and c_single have disagreeing judges
    assert result["advisory_judge_disagreements"] == 2


def test_advisory_judge_none_not_counted() -> None:
    """None advisory_judge is not counted as a disagreement."""
    c = _official(snippet="No judge at all.")
    # No llm_judge key → advisory_judge will be None
    result = mep.measure([c])
    assert result["advisory_judge_disagreements"] == 0


# ---------------------------------------------------------------------------
# 7. Result is JSON-serialisable
# ---------------------------------------------------------------------------


def test_result_is_json_serialisable() -> None:
    """measure() result must be json.dumps-able."""
    candidates = [
        _official(snippet="Json test 1."),
        _community_single(snippet="Json test 2."),
    ]
    result = mep.measure(candidates)
    dumped = json.dumps(result)  # must not raise
    loaded = json.loads(dumped)
    assert loaded["total"] == 2


# ---------------------------------------------------------------------------
# 8. Byte-stability: measure() source contains no datetime.now / date.today
# ---------------------------------------------------------------------------


def test_measure_source_is_deterministic() -> None:
    """measure() must contain no datetime.now or date.today calls."""
    src = inspect.getsource(mep.measure)
    assert "datetime.now" not in src, "measure() must not call datetime.now()"
    assert "date.today" not in src, "measure() must not call date.today()"


# ---------------------------------------------------------------------------
# 9. CLI smoke — orchestrator.py measure-enrich → rc 0, valid JSON
# ---------------------------------------------------------------------------


def test_cli_measure_enrich_subcommand(tmp_path: Path) -> None:
    """CLI smoke: write candidates to a dir, run measure-enrich, assert rc=0 + JSON."""
    snippets = ["Fact alpha.", "Fact beta.", "Fact gamma."]
    for i, snip in enumerate(snippets):
        cand = _official(snippet=snip)
        (tmp_path / f"c{i}.json").write_text(json.dumps(cand), encoding="utf-8")

    scripts_dir = ROOT / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "measure-enrich",
            "--candidates",
            str(tmp_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert result.returncode == 0, f"CLI failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    output = json.loads(result.stdout.strip())
    assert output["total"] == 3
    assert output["admitted"] == 3
    assert output["admit_rate_pct"] == 100.0


# ---------------------------------------------------------------------------
# 10. CLI error handling — nonexistent candidates path → rc 2
# ---------------------------------------------------------------------------


def test_cli_nonexistent_candidates_rc2(tmp_path: Path) -> None:
    """A nonexistent --candidates path must produce rc=2 with no traceback."""
    scripts_dir = ROOT / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "measure-enrich",
            "--candidates",
            str(tmp_path / "does_not_exist.json"),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert result.returncode == 2, f"expected rc=2, got {result.returncode}"
    assert "Traceback" not in result.stderr
    assert "error" in result.stderr.lower()


# ---------------------------------------------------------------------------
# 11. FIX 1 — reason_histogram aggregates across distinct URLs
# ---------------------------------------------------------------------------


def test_reason_histogram_aggregates_across_urls() -> None:
    """Batch with same structural reject reason across distinct URLs → 1 histogram bucket.

    community_two_corr candidates with a single-bad-sha corroboration each
    produce reasons like "corroboration sha256 mismatch (tamper) for url='…'".
    _reason_category must collapse the URL so all candidates share one key.
    """
    # Build 3 candidates each with a tampered first corroboration at a unique URL
    candidates = []
    for i in range(3):
        corr_snip = f"Corroboration alpha {i}."
        bad_sha = "0" * 64  # deliberately wrong
        corr2_snip = "Corroboration beta."
        c: dict = {
            "claim": f"Claim {i}",
            "source_tier": "community",
            "source_url": f"https://reddit.com/r/python/{i}",
            "retrieved_date": "2026-06-15",
            "snippet": f"Community tip {i}.",
            "sha256": canonical_sha(f"Community tip {i}."),
            "corroborations": [
                {
                    "source_url": f"https://unique-host-{i}.example.com/post",
                    "snippet": corr_snip,
                    "sha256": bad_sha,  # tampered → reason with URL embedded
                },
                {
                    "source_url": f"https://blog-{i}.example.io/page",
                    "snippet": corr2_snip,
                    "sha256": canonical_sha(corr2_snip),
                },
            ],
        }
        candidates.append(c)

    result = mep.measure(candidates)

    # There must be exactly ONE histogram key for the corroboration sha mismatch
    # (not 3 separate keys, one per URL).
    sha_mismatch_keys = [
        k for k in result["reason_histogram"] if "corroboration sha256 mismatch" in k
    ]
    assert len(sha_mismatch_keys) == 1, (
        f"expected 1 aggregated sha-mismatch bucket, got {sha_mismatch_keys}"
    )
    # And its count must equal 3 (one per candidate)
    assert result["reason_histogram"][sha_mismatch_keys[0]] == 3, (
        f"expected count 3, got {result['reason_histogram'][sha_mismatch_keys[0]]}"
    )


# ---------------------------------------------------------------------------
# 12. FIX 2 — abstain judge is not a disagreement
# ---------------------------------------------------------------------------


def test_advisory_judge_abstain_not_a_disagreement() -> None:
    """abstain judge on an admit candidate → disagreements==0, abstains==1."""
    c_abstain = _official(snippet="Abstain judge test.")
    c_abstain["llm_judge"] = {"verdict": "abstain", "reason": "insufficient info"}

    result = mep.measure([c_abstain])

    assert result["advisory_judge_disagreements"] == 0, (
        "abstain must not count as disagreement"
    )
    assert result["advisory_judge_abstains"] == 1, (
        "abstain must be counted in advisory_judge_abstains"
    )


def test_advisory_judge_reject_on_admit_is_disagreement() -> None:
    """reject judge on an admit candidate → disagreements==1, abstains==0."""
    c_reject_judge = _official(snippet="Reject judge test.")
    c_reject_judge["llm_judge"] = {"verdict": "reject", "reason": "I disagree"}

    result = mep.measure([c_reject_judge])

    assert result["advisory_judge_disagreements"] == 1
    assert result["advisory_judge_abstains"] == 0


# ---------------------------------------------------------------------------
# 13. FIX 3 — measure() is deterministic and order-independent
# ---------------------------------------------------------------------------


def test_measure_deterministic_across_shuffled_input() -> None:
    """measure(batch) == measure(shuffled_batch) and json.dumps are byte-identical."""
    batch = [
        _official(snippet="Fact alpha."),
        _official(snippet="Fact beta."),
        _community_two_corr(snippet="Community ok."),
        _community_single(snippet="Community bad."),
    ]
    shuffled = copy.copy(batch)
    random.seed(42)
    random.shuffle(shuffled)

    r1 = mep.measure(batch)
    r2 = mep.measure(shuffled)

    assert r1 == r2, f"results differ: {r1} vs {r2}"
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True), (
        "json.dumps with sort_keys differ — by_tier not stable"
    )
