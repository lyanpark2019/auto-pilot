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


# ---------------------------------------------------------------------------
# 14. measure_delta — correct math on known dicts
# ---------------------------------------------------------------------------


def _make_measure_a() -> dict:
    """Known baseline measure() result for delta tests."""
    return {
        "admitted": 2,
        "admit_rate_pct": 66.7,
        "advisory_judge_abstains": 0,
        "advisory_judge_disagreements": 1,
        "by_tier": {
            "community": {"admitted": 1, "rejected": 1},
            "official": {"admitted": 1, "rejected": 0},
        },
        "evidence_complete_pct": 100.0,
        "reason_histogram": {"some reason": 1},
        "rejected": 1,
        "total": 3,
    }


def _make_measure_b() -> dict:
    """Known variant measure() result for delta tests."""
    return {
        "admitted": 3,
        "admit_rate_pct": 100.0,
        "advisory_judge_abstains": 1,
        "advisory_judge_disagreements": 0,
        "by_tier": {
            "community": {"admitted": 2, "rejected": 0},
            "official": {"admitted": 1, "rejected": 0},
        },
        "evidence_complete_pct": 100.0,
        "reason_histogram": {},
        "rejected": 0,
        "total": 3,
    }


def test_measure_delta_scalar_math() -> None:
    """measure_delta scalar keys carry correct a/b/delta values."""
    a = _make_measure_a()
    b = _make_measure_b()
    delta = mep.measure_delta(a, b)

    assert delta["admitted"] == {"a": 2.0, "b": 3.0, "delta": 1.0}
    assert delta["rejected"] == {"a": 1.0, "b": 0.0, "delta": -1.0}
    # admit_rate_pct: 66.7 -> 100.0, delta = 33.3 (float; check approximately)
    assert abs(delta["admit_rate_pct"]["delta"] - 33.3) < 0.01, (
        f"admit_rate_pct delta wrong: {delta['admit_rate_pct']}"
    )
    assert delta["advisory_judge_disagreements"] == {
        "a": 1.0, "b": 0.0, "delta": -1.0
    }
    assert delta["advisory_judge_abstains"] == {"a": 0.0, "b": 1.0, "delta": 1.0}
    assert delta["total"] == {"a": 3.0, "b": 3.0, "delta": 0.0}


def test_measure_delta_by_tier_nesting() -> None:
    """measure_delta by_tier carries nested admitted/rejected deltas per tier."""
    a = _make_measure_a()
    b = _make_measure_b()
    delta = mep.measure_delta(a, b)

    # community: admitted 1->2 (+1), rejected 1->0 (-1)
    assert delta["by_tier"]["community"]["admitted"] == {"a": 1.0, "b": 2.0, "delta": 1.0}
    assert delta["by_tier"]["community"]["rejected"] == {"a": 1.0, "b": 0.0, "delta": -1.0}
    # official: admitted 1->1 (0), rejected 0->0 (0)
    assert delta["by_tier"]["official"]["admitted"] == {"a": 1.0, "b": 1.0, "delta": 0.0}
    assert delta["by_tier"]["official"]["rejected"] == {"a": 0.0, "b": 0.0, "delta": 0.0}


def test_measure_delta_reason_histogram_absent() -> None:
    """reason_histogram is not present in the delta output."""
    a = _make_measure_a()
    b = _make_measure_b()
    delta = mep.measure_delta(a, b)
    assert "reason_histogram" not in delta, (
        "reason_histogram must be omitted from measure_delta output"
    )


def test_measure_delta_keys_are_sorted() -> None:
    """measure_delta output keys are sorted (byte-stable JSON)."""
    delta = mep.measure_delta(_make_measure_a(), _make_measure_b())
    keys = list(delta.keys())
    assert keys == sorted(keys), f"delta keys not sorted: {keys}"


def test_measure_delta_byte_stable() -> None:
    """Same inputs produce identical JSON on two calls (no datetime.now/random)."""
    a = _make_measure_a()
    b = _make_measure_b()
    j1 = json.dumps(mep.measure_delta(a, b), indent=2, sort_keys=True)
    j2 = json.dumps(mep.measure_delta(a, b), indent=2, sort_keys=True)
    assert j1 == j2, "measure_delta is not byte-stable"


def test_measure_delta_source_no_datetime_random() -> None:
    """measure_delta source must contain no datetime.now or random calls."""
    import ast  # noqa: PLC0415
    src = inspect.getsource(mep.measure_delta)
    tree = ast.parse(src)
    call_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                call_names.append(
                    f"{ast.unparse(node.func.value)}.{node.func.attr}"
                )
            elif isinstance(node.func, ast.Name):
                call_names.append(node.func.id)
    now_calls = [c for c in call_names if "now" in c.lower() or "today" in c.lower()]
    random_calls = [c for c in call_names if "random" in c.lower()]
    assert not now_calls, f"measure_delta must not call datetime.now/date.today: {now_calls}"
    assert not random_calls, f"measure_delta must not call random: {random_calls}"


def test_measure_delta_sign_correct() -> None:
    """RED-prove delta sign: b - a, not a - b."""
    # If a.admitted=10, b.admitted=5: delta must be -5, not +5.
    a = {
        "admitted": 10, "admit_rate_pct": 100.0,
        "advisory_judge_abstains": 0, "advisory_judge_disagreements": 0,
        "by_tier": {"official": {"admitted": 10, "rejected": 0}},
        "evidence_complete_pct": 100.0, "reason_histogram": {},
        "rejected": 0, "total": 10,
    }
    b = {
        "admitted": 5, "admit_rate_pct": 50.0,
        "advisory_judge_abstains": 0, "advisory_judge_disagreements": 0,
        "by_tier": {"official": {"admitted": 5, "rejected": 5}},
        "evidence_complete_pct": 100.0, "reason_histogram": {},
        "rejected": 5, "total": 10,
    }
    delta = mep.measure_delta(a, b)
    assert delta["admitted"]["delta"] == -5.0, (
        f"delta sign wrong: expected -5.0 (b - a), got {delta['admitted']['delta']}"
    )
    assert delta["rejected"]["delta"] == 5.0, (
        f"delta sign wrong for rejected: expected +5.0 (b - a), got {delta['rejected']['delta']}"
    )


# ---------------------------------------------------------------------------
# 15. CLI --compare: subprocess test
# ---------------------------------------------------------------------------


def test_cli_compare_two_paths(tmp_path: Path) -> None:
    """CLI --compare BASELINE VARIANT -> valid delta JSON, rc=0."""
    # Baseline dir: 2 official (admitted)
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    for i in range(2):
        (baseline_dir / f"c{i}.json").write_text(
            json.dumps(_official(snippet=f"Baseline fact {i}.")), encoding="utf-8"
        )

    # Variant dir: 3 official (admitted) — admit rate goes up
    variant_dir = tmp_path / "variant"
    variant_dir.mkdir()
    for i in range(3):
        (variant_dir / f"c{i}.json").write_text(
            json.dumps(_official(snippet=f"Variant fact {i}.")), encoding="utf-8"
        )

    scripts_dir = ROOT / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "measure-enrich",
            "--compare",
            str(baseline_dir),
            str(variant_dir),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert result.returncode == 0, (
        f"--compare failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    delta = json.loads(result.stdout.strip())

    # Structure: each scalar key must have a/b/delta
    assert "admitted" in delta, f"missing 'admitted' in delta: {list(delta)}"
    assert set(delta["admitted"]) == {"a", "b", "delta"}, (
        f"unexpected delta shape: {delta['admitted']}"
    )

    # Values: baseline admitted=2, variant admitted=3 → delta=+1
    assert delta["admitted"]["a"] == 2.0
    assert delta["admitted"]["b"] == 3.0
    assert delta["admitted"]["delta"] == 1.0

    # by_tier present and nested
    assert "by_tier" in delta
    assert "official" in delta["by_tier"]
    assert delta["by_tier"]["official"]["admitted"]["delta"] == 1.0

    # reason_histogram must not appear
    assert "reason_histogram" not in delta


def test_cli_compare_missing_path_rc2(tmp_path: Path) -> None:
    """--compare with a nonexistent path -> rc=2, no traceback."""
    scripts_dir = ROOT / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "measure-enrich",
            "--compare",
            str(tmp_path / "noexist_a"),
            str(tmp_path / "noexist_b"),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert result.returncode == 2, f"expected rc=2, got {result.returncode}"
    assert "Traceback" not in result.stderr


def test_cli_candidates_still_works_after_compare_added(tmp_path: Path) -> None:
    """--candidates single-batch path is unaffected by --compare addition."""
    (tmp_path / "c.json").write_text(
        json.dumps(_official(snippet="Compat check.")), encoding="utf-8"
    )
    scripts_dir = ROOT / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "measure-enrich",
            "--candidates",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert result.returncode == 0, (
        f"--candidates failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    out = json.loads(result.stdout.strip())
    assert out["total"] == 1
    assert out["admitted"] == 1
