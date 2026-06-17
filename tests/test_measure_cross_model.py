"""Tests for scripts/measure_cross_model.py — cross-model convergence instrument.

Deterministic: feeds canned review records to the real measure(), which runs the
real miner (scan_reviewer_findings + bump_or_create) over a throwaway ledger.
HOME is isolated per test so the attest key never touches the real home dir.
No live models.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import measure_cross_model as mx  # noqa: E402
import measure_cross_model_collect as mc  # noqa: E402

_DEFECTS = [
    {"name": "percentile-p1-boundary", "file_basename": "stats.py",
     "expected_class": "index-out-of-bounds"},
    {"name": "first-token-empty-input", "file_basename": "parse.py",
     "expected_class": "unguarded-empty-input"},
]


def _finding(file: str, cls: str | None, issue: str, line: int = 8) -> dict:
    return {"file": file, "line": line, "issue": issue, "class": cls}


def _rec(model: str, pass_n: int, findings: list, verdict: str = "REJECT") -> dict:
    return {"model": model, "pass": f"pass-{pass_n}", "verdict": verdict,
            "findings": findings, "error": False}


def _measure(reviews: list, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    work = tmp_path / "work"
    work.mkdir(parents=True, exist_ok=True)
    return mx.measure(reviews, _DEFECTS, work_dir=work)


def _defect(result: dict, name: str) -> dict:
    return next(d for d in result["per_defect"] if d["defect"] == name)


def test_both_models_agree_collapses_and_promotes(tmp_path, monkeypatch):
    reviews = [
        _rec("codex-reviewer", p, [_finding("a/stats.py", "index-out-of-bounds",
                                            f"s[k] out of range at p=1.0 (variant {p})")])
        for p in (1, 2, 3)
    ] + [
        _rec("claude-reviewer", p, [_finding("a/stats.py", "index-out-of-bounds",
                                             f"index k==len(s) overflows (phrasing {p})")])
        for p in (1, 2, 3)
    ]
    res = _measure(reviews, tmp_path, monkeypatch)
    d = _defect(res, "percentile-p1-boundary")
    assert d["cross_model_agree"] is True
    assert d["cross_model_promotable"] is True
    # one fingerprint, distinct_runs == 6 (3 codex + 3 claude passes), spans both.
    assert len(d["fingerprints"]) == 1
    fp = d["fingerprints"][0]
    assert fp["distinct_runs"] == 6
    assert fp["spans_both_models"] is True
    # only stats.py is measurable here (parse.py unreported) → 1/1 measurable defects converged.
    assert res["overall"]["cross_model_convergence_pct"] == 100.0
    assert res["overall"]["defects_measurable"] == 1


def test_models_disagree_fragments_no_cross_model_promotion(tmp_path, monkeypatch):
    reviews = [
        _rec("codex-reviewer", p, [_finding("a/stats.py", "index-out-of-bounds",
                                            f"boundary index (v{p})")])
        for p in (1, 2, 3)
    ] + [
        _rec("claude-reviewer", p, [_finding("a/stats.py", "off-by-one",
                                             f"k is one past the end (v{p})")])
        for p in (1, 2, 3)
    ]
    res = _measure(reviews, tmp_path, monkeypatch)
    d = _defect(res, "percentile-p1-boundary")
    assert d["cross_model_agree"] is False
    assert d["cross_model_promotable"] is False
    # two single-model fingerprints; each promotable on its own, neither spans both.
    assert len(d["fingerprints"]) == 2
    assert all(not fp["spans_both_models"] for fp in d["fingerprints"])
    assert all(fp["promotable"] for fp in d["fingerprints"])
    assert res["overall"]["defects_cross_model_promotable"] == 0


def test_codex_abstain_counted_claude_only_not_cross_model(tmp_path, monkeypatch):
    reviews = [
        _rec("codex-reviewer", 1, [], verdict="ABSTAIN"),
        _rec("claude-reviewer", 1, [_finding("a/parse.py", "unguarded-empty-input",
                                             "tokens[0] on empty split")]),
        _rec("claude-reviewer", 2, [_finding("a/parse.py", "unguarded-empty-input",
                                             "empty input deref")]),
    ]
    res = _measure(reviews, tmp_path, monkeypatch)
    assert res["abstain"] == {"codex-reviewer": 1}
    d = _defect(res, "first-token-empty-input")
    assert d["both_models_reported"] is False
    assert d["cross_model_agree"] is False
    # claude reached distinct_runs==2 (promotable) but single-model → NOT cross-model.
    assert d["cross_model_promotable"] is False
    assert any(fp["promotable"] and not fp["spans_both_models"]
               for fp in d["fingerprints"])


def test_byte_stable_across_input_order(tmp_path, monkeypatch):
    reviews = [
        _rec("codex-reviewer", 1, [_finding("a/stats.py", "index-out-of-bounds", "x")]),
        _rec("claude-reviewer", 1, [_finding("a/stats.py", "index-out-of-bounds", "y")]),
        _rec("claude-reviewer", 2, [_finding("a/parse.py", "unguarded-empty-input", "z")]),
        _rec("codex-reviewer", 2, [_finding("a/parse.py", "off-by-one", "w")]),
    ]
    first = json.dumps(_measure(list(reviews), tmp_path / "a", monkeypatch), sort_keys=True)
    shuffled = list(reviews)
    random.Random(1).shuffle(shuffled)
    second = json.dumps(_measure(shuffled, tmp_path / "b", monkeypatch), sort_keys=True)
    assert first == second


def test_cli_smoke_over_runs_dir(tmp_path):
    # NOTE: do NOT override HOME here — the subprocess re-resolves user site-packages
    # (~/Library/Python/X.Y/...) from HOME at startup, and a tmp HOME hides jsonschema's
    # `referencing` dep. The attest key (real home) only signs a discarded tempdir ledger.
    runs = tmp_path / "runs"
    for model, cls in (("codex-reviewer", "index-out-of-bounds"),
                       ("claude-reviewer", "index-out-of-bounds")):
        d = runs / model / "pass-1"
        d.mkdir(parents=True)
        (d / "review.json").write_text(json.dumps({
            "schema_version": 1, "reviewer": model, "contract_id": "c1",
            "verdict": "REJECT", "scope_check": "PASS",
            "findings": [{"severity": "P1", "file": "a/stats.py", "line": 8,
                          "issue": "boundary", "class": cls, "fix": "guard",
                          "finding_hash": "a" * 64}],
            "verify_rerun": {"cmd": "x", "exit_code": 1},
            "reviewer_meta": {"model": model, "started_at": "2026-01-01T00:00:00Z",
                              "ended_at": "2026-01-01T00:00:01Z"},
        }))
    defects = tmp_path / "defects.json"
    defects.write_text(json.dumps({"defects": _DEFECTS}))
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "orchestrator.py"),
         "measure-cross-model", "--runs", str(runs), "--defects", str(defects), "--json"],
        capture_output=True, text=True, cwd=str(ROOT / "scripts"),
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    d = next(x for x in out["per_defect"] if x["defect"] == "percentile-p1-boundary")
    assert d["cross_model_agree"] is True
    assert d["cross_model_promotable"] is True


# --- producer (measure_cross_model_collect) pure-logic tests, no live models ---

def test_extract_findings_takes_last_findings_object():
    text = ('chatter {"findings":[{"file":"a"}]} more prose '
            'final {"findings":[{"file":"stats.py","class":"index-out-of-bounds"}]} tail')
    f = mc.extract_findings(text)
    assert f == [{"file": "stats.py", "class": "index-out-of-bounds"}]


def test_extract_findings_none_when_absent():
    assert mc.extract_findings("no json here") is None
    assert mc.extract_findings('{"verdict":"APPROVE"}') is None


def test_claude_text_unwraps_result_envelope():
    raw = json.dumps({"type": "result", "result": '{"findings":[]}'})
    assert mc._claude_text(raw) == '{"findings":[]}'
    assert mc._claude_text("plain text") == "plain text"


def test_codex_text_reconstructs_decoded_assistant_text():
    # codex --json emits JSONL events; the findings JSON lives escaped inside an event.
    payload = '{"findings":[{"file":"parse.py","class":"unguarded-empty-input"}]}'
    raw = "\n".join([
        json.dumps({"type": "thinking", "text": "considering"}),
        json.dumps({"type": "message", "content": payload}),
    ])
    decoded = mc._codex_text(raw)
    assert mc.extract_findings(decoded) == [
        {"file": "parse.py", "class": "unguarded-empty-input"}]


def test_shape_review_is_schema_valid_and_round_trips(tmp_path):
    from _dispatch import read_review  # noqa: PLC0415
    rj = tmp_path / "review.json"
    review = mc._shape_review("codex-reviewer",
                              [{"file": "a/stats.py", "line": 8, "severity": "P1",
                                "issue": "boundary", "class": "index-out-of-bounds",
                                "fix": "guard"}], None)
    rj.write_text(json.dumps(review))
    data = read_review(rj)  # raises MalformedReviewError if invalid
    assert data["findings"][0]["class"] == "index-out-of-bounds"
    assert len(data["findings"][0]["finding_hash"]) == 64


def test_fail_reason_detects_usage_limit_vs_generic():
    usage = "\n".join([
        json.dumps({"type": "turn.started"}),
        json.dumps({"type": "turn.failed",
                    "error": {"message": "You've hit your usage limit."}}),
    ])
    assert mc._fail_reason("codex-reviewer", usage, "") == "codex-reviewer-usage-limit"
    generic = json.dumps({"type": "error", "message": "boom"})
    assert mc._fail_reason("codex-reviewer", generic, "") == "codex-reviewer-exec-failed"


def test_shape_review_abstain_has_reason(tmp_path):
    from _dispatch import read_review  # noqa: PLC0415
    rj = tmp_path / "review.json"
    review = mc._shape_review("codex-reviewer", None, "codex-reviewer-timeout")
    rj.write_text(json.dumps(review))
    data = read_review(rj)
    assert data["verdict"] == "ABSTAIN"
    assert data["reviewer_meta"]["abstain_reason"] == "codex-reviewer-timeout"


# --- review-fix regression tests (cold-review findings) ---

def test_byte_stable_under_modal_class_tie(tmp_path, monkeypatch):
    # A modal tie (1-1) must NOT make the headline metric depend on input order.
    reviews = [
        _rec("claude-reviewer", 1, [_finding("a/stats.py", "index-out-of-bounds", "a")]),
        _rec("claude-reviewer", 2, [_finding("a/stats.py", "off-by-one", "b")]),
        _rec("codex-reviewer", 1, [_finding("a/stats.py", "index-out-of-bounds", "c")]),
        _rec("codex-reviewer", 2, [_finding("a/stats.py", "off-by-one", "d")]),
    ]
    first = json.dumps(_measure(list(reviews), tmp_path / "a", monkeypatch), sort_keys=True)
    shuffled = list(reviews)
    random.Random(7).shuffle(shuffled)
    second = json.dumps(_measure(shuffled, tmp_path / "b", monkeypatch), sort_keys=True)
    assert first == second
    # deterministic modal = lexicographically smallest of the tied classes.
    res = _measure(list(reviews), tmp_path / "c", monkeypatch)
    assert _defect(res, "percentile-p1-boundary")["claude_modal_class"] == "index-out-of-bounds"


def test_prose_only_finding_not_measurable(tmp_path, monkeypatch):
    # both models flag the file, but claude gives no in-vocab class → NOT measurable,
    # so it cannot drag convergence_pct toward 0.
    reviews = [
        _rec("codex-reviewer", 1, [_finding("a/parse.py", "unguarded-empty-input", "x")]),
        _rec("claude-reviewer", 1, [_finding("a/parse.py", None, "some prose issue")]),
    ]
    res = _measure(reviews, tmp_path, monkeypatch)
    d = _defect(res, "first-token-empty-input")
    assert d["both_models_reported"] is True
    assert d["both_models_classified"] is False
    assert d["cross_model_agree"] is False
    assert res["overall"]["defects_measurable"] == 0
    assert res["overall"]["cross_model_convergence_pct"] == 0.0


def test_duplicate_basename_defects_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    work = tmp_path / "w"
    work.mkdir(parents=True, exist_ok=True)
    dup = [{"name": "a", "file_basename": "stats.py"},
           {"name": "b", "file_basename": "stats.py"}]
    with pytest.raises(ValueError, match="share basename"):
        mx.measure([], dup, work_dir=work)


def test_extract_findings_unbalanced_brace_inside_issue_string():
    # F1: an UNBALANCED brace inside the issue string is the real desync case — a naive
    # depth counter never returns to 0 and drops the finding; raw_decode is string-aware.
    text = ('{"findings":[{"file":"x.py","issue":"loop body opens with {",'
            '"class":"index-out-of-bounds"}]}')
    f = mc.extract_findings(text)
    assert f == [{"file": "x.py", "issue": "loop body opens with {",
                  "class": "index-out-of-bounds"}]


def test_collect_clears_stale_passes(tmp_path, monkeypatch):
    # F4: re-running to the same --out must not leave a prior run's higher passes behind.
    monkeypatch.setattr(mc, "_run_claude", lambda prompt: ('{"findings":[]}', None))
    out = tmp_path / "runs"
    mc.collect("diff", out, ["claude-reviewer"], passes=3, codex_effort="low")
    assert (out / "claude-reviewer" / "pass-3" / "review.json").exists()
    mc.collect("diff", out, ["claude-reviewer"], passes=2, codex_effort="low")
    assert not (out / "claude-reviewer" / "pass-3").exists()
    assert (out / "claude-reviewer" / "pass-2" / "review.json").exists()


def test_claude_envelope_fail_classifies_usage_block():
    # F2: claude -p reports a block by exiting 0 with is_error in the envelope.
    raw = json.dumps({"type": "result", "is_error": True, "result": "5-hour limit reached"})
    assert mc._claude_envelope_fail(raw) == "claude-reviewer-usage-limit"
    assert mc._claude_envelope_fail(json.dumps({"type": "result", "result": "{}"})) is None


def test_fail_reason_extra_throttle_phrasings():
    # F3: rate-limit / limit-reached phrasings classify as usage-limit, not exec-failed.
    for phrase in ("You have been rate limited.", "5-hour limit reached", "quota exceeded"):
        ev = json.dumps({"type": "error", "message": phrase})
        assert mc._fail_reason("codex-reviewer", ev, "") == "codex-reviewer-usage-limit"
