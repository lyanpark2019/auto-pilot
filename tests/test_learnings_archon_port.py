"""Archon-port tests for scripts/_learnings.py: --ledger-dir override + --sanitized anti-spoiler render.

Split out of test_learnings.py to keep that file under the module-size budget."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _learnings as lr  # noqa: E402
from test_learnings import _valid_ticket, _write_ticket  # noqa: E402


def test_resolve_learnings_ledger_override_selects_ticket(tmp_path):
    """A ticket seeded in a tmp ledger is selected via ledger_dir_override.

    No mock of ledger_dir — the override must win over the per-repo default.
    """
    tmp_ledger = tmp_path / "durable"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(tmp_ledger, ticket)

    dest_dir = tmp_path / "bundle-override"
    result = lr.resolve_learnings(
        tmp_path / "unrelated-repo", ["scripts/_contract.py"], dest_dir,
        ledger_dir_override=tmp_ledger,
    )
    assert result is not None and result.exists()


def test_resolve_learnings_default_ledger_blind_to_tmp_ticket(tmp_path):
    """Without ledger_dir_override, the tmp ledger ticket is invisible.

    The default ledger (mocked to an empty dir) is read, so the seeded tmp
    ticket is not selected — proving the override is what surfaces it above.
    """
    import unittest.mock as mock

    tmp_ledger = tmp_path / "durable"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(tmp_ledger, ticket)

    empty_default = tmp_path / "empty-default"
    dest_dir = tmp_path / "bundle-noverride"
    with mock.patch("_learnings.ledger_dir", return_value=empty_default):
        result = lr.resolve_learnings(
            tmp_path, ["scripts/_contract.py"], dest_dir,
        )
    assert result is None, "tmp ledger ticket must be invisible without override"


# ---------------------------------------------------------------------------
# Task 5 — render_learnings_sanitized: class-level nudge only (codex P0-1)
# ---------------------------------------------------------------------------

def _leaky_ticket() -> dict:
    """A gate-passed ticket whose evidence carries literal defect text + file:line."""
    t = _valid_ticket(
        state="candidate", distinct_runs=2,
        source_path="scripts/_contract.py",
        run_id="run-leaky-9",
        snippet="off-by-one at scripts/_contract.py:142 in write_contract loop",
    )
    t["pattern"] = "off-by-one"  # the canonical defect class
    return t


def test_render_sanitized_keeps_class_and_generic_instruction():
    body = lr.render_learnings_sanitized([_leaky_ticket()])
    assert "off-by-one" in body, "the defect class must survive"
    assert "check for them" in body, "a generic instruction must be present"


def test_render_sanitized_leaks_no_identifying_fields():
    """The sanitized render contains NONE of: issue title, evidence string,
    file path, run id, or line number."""
    body = lr.render_learnings_sanitized([_leaky_ticket()])
    # issue title / evidence snippet text
    assert "write_contract loop" not in body
    assert "off-by-one at scripts" not in body
    # run id
    assert "run-leaky-9" not in body
    # file path
    assert "scripts/_contract.py" not in body
    assert "_contract.py" not in body
    # line number
    assert "142" not in body


def test_render_sanitized_is_byte_stable_and_dedupes_class():
    """Two tickets of the same class collapse to one nudge; order-independent."""
    t1 = _leaky_ticket()
    t1["fingerprint"] = "a" * 64
    t2 = _leaky_ticket()
    t2["fingerprint"] = "b" * 64
    out1 = lr.render_learnings_sanitized([t1, t2])
    out2 = lr.render_learnings_sanitized([t2, t1])
    assert out1 == out2, "sanitized render must be byte-stable regardless of order"
    assert out1.count("`off-by-one`") == 1, "same class must dedupe to one nudge"


def test_resolve_learnings_sanitized_mode_strips_leaks(tmp_path):
    """resolve_learnings(sanitized=True) keeps selection but writes the nudge-only body."""
    tmp_ledger = tmp_path / "durable"
    _write_ticket(tmp_ledger, _leaky_ticket())

    dest_dir = tmp_path / "bundle-sani"
    result = lr.resolve_learnings(
        tmp_path / "unrelated-repo", ["scripts/_contract.py"], dest_dir,
        ledger_dir_override=tmp_ledger, sanitized=True,
    )
    assert result is not None
    body = result.read_text()
    assert "off-by-one" in body and "check for them" in body
    assert "scripts/_contract.py" not in body
    assert "run-leaky-9" not in body
    assert "142" not in body


def test_resolve_learnings_full_mode_still_renders_evidence(tmp_path):
    """Without sanitized=True the full render (with evidence) is unchanged."""
    tmp_ledger = tmp_path / "durable"
    _write_ticket(tmp_ledger, _leaky_ticket())

    dest_dir = tmp_path / "bundle-full"
    result = lr.resolve_learnings(
        tmp_path / "unrelated-repo", ["scripts/_contract.py"], dest_dir,
        ledger_dir_override=tmp_ledger, sanitized=False,
    )
    assert result is not None
    body = result.read_text()
    # full render keeps the evidence sample (run id + snippet)
    assert "run-leaky-9" in body


# ---------------------------------------------------------------------------
# Fix B — sanitized render emits controlled-vocab classes ONLY (experiment-validity)
# ---------------------------------------------------------------------------

def test_render_sanitized_skips_free_form_title_pattern():
    """A ticket whose pattern is a free-form leaky TITLE is dropped, not printed.

    For an out-of-vocab / class-less reviewer finding the miner falls back to
    keying on the normalized issue prose, so the seeded ``pattern`` is the issue
    TITLE — printing it would spoil the A/B oracle.
    """
    leaky_title = "sql string built by concatenation in build_query"
    t = _leaky_ticket()
    t["pattern"] = leaky_title
    body = lr.render_learnings_sanitized([t])
    assert leaky_title not in body, "free-form title must not leak into the nudge"
    assert "build_query" not in body
    assert "concatenation" not in body
    # nothing of vocabulary value to inject → no nudge bullet
    assert "check for them" not in body


def test_render_sanitized_skips_out_of_vocab_class():
    """class:'none' / arbitrary out-of-vocab pattern → skipped (no nudge)."""
    for bogus in ("none", "some-made-up-class", ""):
        t = _leaky_ticket()
        t["pattern"] = bogus
        body = lr.render_learnings_sanitized([t])
        assert "check for them" not in body, f"{bogus!r} must be skipped"
        if bogus:
            assert bogus not in body


def test_render_sanitized_renders_in_vocab_class_among_leaky():
    """An in-vocab ticket still renders its class nudge even alongside a leaky one."""
    in_vocab = _leaky_ticket()
    in_vocab["pattern"] = "injection"  # controlled vocab
    in_vocab["fingerprint"] = "c" * 64
    leaky = _leaky_ticket()
    leaky["pattern"] = "sql string built by concatenation in build_query"
    leaky["fingerprint"] = "d" * 64
    body = lr.render_learnings_sanitized([in_vocab, leaky])
    assert "`injection`" in body and "check for them" in body
    assert "build_query" not in body, "the leaky free-form title stays out"
