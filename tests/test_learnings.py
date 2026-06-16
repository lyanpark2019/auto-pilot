"""Tests for scripts/_learnings.py and its integration with _contract.snapshot_context."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _contract  # noqa: E402
import _learnings as lr  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "contracts" / "sample_contract.json"


def _evidence_entry(
    run_id: str = "run-1",
    snippet: str = "worker skipped verify",
    source_path: str = "",
) -> dict:
    """Build one evidence item in the shape ``_apply_bump`` now produces.

    ``source_path`` is included ONLY when non-empty — matching the real miner output.
    """
    entry: dict = {"run_id": run_id, "snippet": snippet}
    if source_path:
        entry["source_path"] = source_path
    return entry


def _valid_ticket(
    fingerprint: str = "a" * 64,
    state: str = "candidate",
    source_path: str = "scripts/_contract.py",
    run_id: str = "run-1",
    snippet: str = "worker skipped verify",
    distinct_runs: int = 2,
) -> dict:
    """Build a valid improvement ticket with evidence in the real miner shape.

    ``state="candidate"`` with ``distinct_runs=2`` passes ``is_promotable()``
    for source="reviewer-finding" (threshold=2) — the gate-passed condition.
    Use ``state="promoted"`` for the fully-promoted path, and
    ``distinct_runs=1`` to produce a sub-threshold (excluded) ticket.

    Evidence entries are built by ``_evidence_entry`` — ``source_path`` is
    present only when non-empty, mirroring what ``_apply_bump`` actually writes.
    """
    return {
        "schema_version": 1,
        "fingerprint": fingerprint,
        "state": state,
        "pattern": "worker skipped verify gate",
        "source": "reviewer-finding",
        "candidate_asset": "hook",
        "occurrences": distinct_runs,
        "distinct_runs": distinct_runs,
        "first_seen": "2026-06-09T00:00:00Z",
        "last_seen": "2026-06-10T00:00:00Z",
        "plugin_version": "0.9.0",
        "repo_fingerprint": "abc123",
        "evidence": [
            _evidence_entry(run_id=run_id, snippet=snippet, source_path=source_path)
        ],
        "promotion_gate": {"tests_pass": None, "ci_pass": None, "user_approved": None},
    }


def _write_ticket(ledger: Path, ticket: dict) -> None:
    ledger.mkdir(parents=True, exist_ok=True)
    fp = ticket["fingerprint"]
    (ledger / f"{fp}.json").write_text(json.dumps(ticket, indent=2) + "\n")


def _bind_snapshot_to_contract(dest_dir: Path, shas: _contract.SnapshotShas) -> None:
    contract = json.loads(FIXTURE.read_text())
    contract["snapshot_shas"]["spec"] = shas.spec
    contract["snapshot_shas"]["claude_md_chain"] = shas.claude_md_chain
    contract["context_bundle_path"] = str(dest_dir / "context-bundle")
    if shas.project_context is not None:
        contract["snapshot_shas"]["project_context"] = shas.project_context
    if shas.learnings is not None:
        contract["snapshot_shas"]["learnings"] = shas.learnings
    _contract.write_contract(contract, dest_dir / "contract.json")


# ---------------------------------------------------------------------------
# (a) scope match selects a promotable ticket — evidence in real miner shape
# ---------------------------------------------------------------------------

def test_select_tickets_matches_promotable_by_scope(tmp_path):
    """candidate ticket with distinct_runs=2 passes is_promotable for reviewer-finding.

    Evidence built in real shape: source_path present because reviewer named a file.
    """
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    results = lr.select_tickets(ledger, ["scripts/_contract.py"])
    assert len(results) == 1
    assert results[0]["fingerprint"] == "a" * 64


def test_select_tickets_matches_promoted_state(tmp_path):
    """fully-promoted ticket is selected regardless of is_promotable."""
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="promoted", distinct_runs=2,
                           source_path="src/auth/login.py")
    ticket["promotion_gate"] = {
        "tests_pass": True, "ci_pass": True, "user_approved": True,
    }
    _write_ticket(ledger, ticket)

    results = lr.select_tickets(ledger, ["src/auth/login.py"])
    assert len(results) == 1


def test_select_tickets_matches_dir_prefix_scope(tmp_path):
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/sub/module.py")
    _write_ticket(ledger, ticket)

    results = lr.select_tickets(ledger, ["scripts/"])
    assert len(results) == 1


# ---------------------------------------------------------------------------
# (a-real) evidence without source_path does NOT match — real miner no-file case
# ---------------------------------------------------------------------------

def test_select_tickets_no_file_ref_is_not_injected(tmp_path):
    """A ticket whose evidence has no source_path is NOT injected (conservative).

    This is the doom-loop / insight case where the miner produces no file ref.
    The old asset-substring fallback would have injected it; we removed that.
    """
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2, source_path="")
    _write_ticket(ledger, ticket)

    results = lr.select_tickets(ledger, ["scripts/_contract.py"])
    assert results == [], "ticket with no file evidence must not be scope-matched"


# ---------------------------------------------------------------------------
# (b) no-overlap selects nothing
# ---------------------------------------------------------------------------

def test_select_tickets_no_overlap_returns_empty(tmp_path):
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    results = lr.select_tickets(ledger, ["src/auth/login.py"])
    assert results == []


def test_select_tickets_absent_ledger_returns_empty(tmp_path):
    ledger = tmp_path / "does-not-exist"
    results = lr.select_tickets(ledger, ["scripts/_contract.py"])
    assert results == []


# ---------------------------------------------------------------------------
# (c) candidate/un-promotable state is excluded
# ---------------------------------------------------------------------------

def test_select_tickets_excludes_sub_threshold_candidate(tmp_path):
    """candidate with distinct_runs=1 is below threshold for reviewer-finding (threshold=2)."""
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=1,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    results = lr.select_tickets(ledger, ["scripts/_contract.py"])
    assert results == []


def test_select_tickets_excludes_rejected_state(tmp_path):
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="rejected", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    results = lr.select_tickets(ledger, ["scripts/_contract.py"])
    assert results == []


def test_select_tickets_excludes_sub_threshold_doom_loop(tmp_path):
    """doom-loop source has threshold=3; distinct_runs=2 is excluded."""
    ledger = tmp_path / "ledger"
    ticket = {
        "schema_version": 1,
        "fingerprint": "b" * 64,
        "state": "candidate",
        "pattern": "pivot repeated",
        "source": "doom-loop",
        "candidate_asset": "hook",
        "occurrences": 2,
        "distinct_runs": 2,
        "first_seen": "2026-06-09T00:00:00Z",
        "last_seen": "2026-06-10T00:00:00Z",
        "plugin_version": "0.9.0",
        "repo_fingerprint": "abc123",
        "evidence": [
            {"run_id": "r1", "snippet": "pivot detected"},
        ],
        "promotion_gate": {"tests_pass": None, "ci_pass": None, "user_approved": None},
    }
    _write_ticket(ledger, ticket)

    results = lr.select_tickets(ledger, ["scripts/x.py"])
    assert results == []


# ---------------------------------------------------------------------------
# (d) renderer output is byte-stable
# ---------------------------------------------------------------------------

def test_render_learnings_is_byte_stable():
    tickets = [
        _valid_ticket(fingerprint="a" * 64, distinct_runs=2),
        _valid_ticket(fingerprint="b" * 64, distinct_runs=2),
    ]
    out1 = lr.render_learnings(tickets)
    out2 = lr.render_learnings(list(reversed(tickets)))
    assert out1 == out2, "render_learnings must be byte-stable regardless of input order"


def test_render_learnings_contains_fingerprint_prefix():
    ticket = _valid_ticket(state="candidate", distinct_runs=2)
    body = lr.render_learnings([ticket])
    assert "aaaaaaaaaaaa" in body


def test_render_learnings_empty_list():
    body = lr.render_learnings([])
    assert "# Injected learnings" in body


# ---------------------------------------------------------------------------
# (e) snapshot_context pins learnings + verify_snapshots rejects tamper
# ---------------------------------------------------------------------------

def test_snapshot_context_pins_learnings(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("# rules\n")
    learnings_src = tmp_path / "learnings.md"
    learnings_src.write_text("# Injected learnings\n\nhello\n")

    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)

    shas = _contract.snapshot_context(
        dest_dir, spec, [claude_md], learnings_path=learnings_src
    )

    assert shas.learnings is not None
    assert len(shas.learnings) == 64
    bundle = dest_dir / "context-bundle"
    assert (bundle / "learnings.md").exists()
    assert "learnings.md" in (bundle / "MANIFEST.txt").read_text()


def test_snapshot_context_no_learnings_path(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)

    shas = _contract.snapshot_context(dest_dir, spec, [])
    assert shas.learnings is None
    bundle = dest_dir / "context-bundle"
    assert not (bundle / "learnings.md").exists()
    assert "learnings.md" not in (bundle / "MANIFEST.txt").read_text()


def test_verify_snapshots_rejects_tampered_learnings(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    learnings_src = tmp_path / "learnings.md"
    learnings_src.write_text("# Injected learnings\nsome learning\n")

    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)

    shas = _contract.snapshot_context(dest_dir, spec, [], learnings_path=learnings_src)
    _bind_snapshot_to_contract(dest_dir, shas)

    _contract.verify_snapshots(dest_dir)

    (dest_dir / "context-bundle" / "learnings.md").write_text("TAMPERED\n")
    with pytest.raises(_contract.SnapshotMismatchError, match="learnings.md sha mismatch"):
        _contract.verify_snapshots(dest_dir)


def test_verify_snapshots_rejects_declared_but_missing_learnings(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    learnings_src = tmp_path / "learnings.md"
    learnings_src.write_text("# Injected learnings\nsome learning\n")

    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)

    shas = _contract.snapshot_context(dest_dir, spec, [], learnings_path=learnings_src)
    _bind_snapshot_to_contract(dest_dir, shas)

    (dest_dir / "context-bundle" / "learnings.md").unlink()
    with pytest.raises(_contract.SnapshotMismatchError, match="declared.*absent"):
        _contract.verify_snapshots(dest_dir)


def test_verify_snapshots_passes_without_learnings(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)

    shas = _contract.snapshot_context(dest_dir, spec, [])
    _bind_snapshot_to_contract(dest_dir, shas)

    _contract.verify_snapshots(dest_dir)


def test_snapshot_context_learnings_path_is_bundle_file_no_samefile_error(tmp_path):
    """resolve_learnings writes into the bundle; the PM threads that SAME path back
    into snapshot_context. The same-file guard (B2) must avoid SameFileError and
    still record the learnings sha + verify cleanly.
    """
    import unittest.mock as mock

    spec = tmp_path / "spec.md"
    spec.write_text("# spec\n")
    ledger = tmp_path / "ledger"
    _write_ticket(ledger, _valid_ticket(state="candidate", distinct_runs=2,
                                        source_path="scripts/_contract.py"))

    dest_dir = tmp_path / "contract" / "round-1"
    dest_dir.mkdir(parents=True)
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        learnings_path = lr.resolve_learnings(tmp_path, ["scripts/_contract.py"], dest_dir)
    assert learnings_path == dest_dir / "context-bundle" / "learnings.md"

    # learnings_path IS the bundle file — must not raise SameFileError.
    shas = _contract.snapshot_context(dest_dir, spec, [], learnings_path=learnings_path)
    assert shas.learnings is not None and len(shas.learnings) == 64
    _bind_snapshot_to_contract(dest_dir, shas)
    _contract.verify_snapshots(dest_dir)


# ---------------------------------------------------------------------------
# Integration: resolve_learnings writes the file
# ---------------------------------------------------------------------------

def test_resolve_learnings_returns_path_when_match(tmp_path):
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    import unittest.mock as mock

    dest_dir = tmp_path / "bundle-dir"
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        result = lr.resolve_learnings(tmp_path, ["scripts/_contract.py"], dest_dir)

    assert result is not None
    assert result.exists()
    assert result.name == "learnings.md"


def test_resolve_learnings_returns_none_when_no_match(tmp_path):
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    import unittest.mock as mock

    dest_dir = tmp_path / "bundle-dir"
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        result = lr.resolve_learnings(tmp_path, ["src/unrelated/file.py"], dest_dir)

    assert result is None
    # Always-write contract (D2 PR-2): blind path still writes the marker file.
    marker = dest_dir / "context-bundle" / "learnings.md"
    assert marker.exists() and "No gate-passed learnings" in marker.read_text()


# ---------------------------------------------------------------------------
# Integration: miner → ledger → resolver (real _apply_bump shape, not fabricated)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# (f) gated=False includes sub-threshold and rejected tickets the gate blocks
# ---------------------------------------------------------------------------

def test_select_tickets_gated_false_includes_sub_threshold(tmp_path):
    """select_tickets(gated=False) includes a sub-threshold ticket that gated=True blocks."""
    ledger = tmp_path / "ledger"
    sub_threshold = _valid_ticket(fingerprint="f" * 64, state="candidate",
                                  distinct_runs=1, source_path="scripts/_contract.py")
    gate_passed = _valid_ticket(fingerprint="a" * 64, state="candidate",
                                distinct_runs=2, source_path="scripts/_contract.py")
    _write_ticket(ledger, sub_threshold)
    _write_ticket(ledger, gate_passed)

    gated_results = lr.select_tickets(ledger, ["scripts/"])
    ungated_results = lr.select_tickets(ledger, ["scripts/"], gated=False)

    gated_fps = {t["fingerprint"] for t in gated_results}
    ungated_fps = {t["fingerprint"] for t in ungated_results}

    assert "f" * 64 not in gated_fps, "sub-threshold ticket must be excluded by gate"
    assert "f" * 64 in ungated_fps, "sub-threshold ticket must be included when gated=False"
    assert "a" * 64 in gated_fps, "gate-passed ticket must appear in gated results"
    assert "a" * 64 in ungated_fps, "gate-passed ticket must appear in ungated results"


def test_select_tickets_gated_false_includes_rejected(tmp_path):
    """select_tickets(gated=False) includes a rejected ticket that gated=True blocks."""
    ledger = tmp_path / "ledger"
    rejected = _valid_ticket(fingerprint="e" * 64, state="rejected",
                             distinct_runs=2, source_path="scripts/_contract.py")
    _write_ticket(ledger, rejected)

    gated_results = lr.select_tickets(ledger, ["scripts/"])
    ungated_results = lr.select_tickets(ledger, ["scripts/"], gated=False)

    assert gated_results == [], "rejected ticket must be excluded by gate"
    assert len(ungated_results) == 1, "rejected ticket must appear when gated=False"
    assert ungated_results[0]["fingerprint"] == "e" * 64


# ---------------------------------------------------------------------------
# (g) AUTO_PILOT_DISABLE_LEARNINGS env kill-switch
# ---------------------------------------------------------------------------

def test_resolve_learnings_disabled_by_env(tmp_path, monkeypatch):
    """AUTO_PILOT_DISABLE_LEARNINGS=1 → resolve_learnings returns None unconditionally."""
    import unittest.mock as mock

    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    monkeypatch.setenv("AUTO_PILOT_DISABLE_LEARNINGS", "1")
    dest_dir = tmp_path / "bundle-dir"
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        result = lr.resolve_learnings(tmp_path, ["scripts/_contract.py"], dest_dir)

    assert result is None, "env kill-switch must prevent injection"
    # Always-write contract (D2 PR-2): the marker IS written even when disabled,
    # so the dispatch gate can treat file-presence as "resolve ran". result=None
    # still signals blind (no real tickets injected).
    marker = dest_dir / "context-bundle" / "learnings.md"
    assert marker.exists(), "blind/disabled path must still write the marker file"
    assert "No gate-passed learnings" in marker.read_text()


def test_resolve_learnings_not_disabled_when_env_unset(tmp_path, monkeypatch):
    """Without AUTO_PILOT_DISABLE_LEARNINGS, resolve_learnings proceeds normally."""
    import unittest.mock as mock

    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    monkeypatch.delenv("AUTO_PILOT_DISABLE_LEARNINGS", raising=False)
    dest_dir = tmp_path / "bundle-dir2"
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        result = lr.resolve_learnings(tmp_path, ["scripts/_contract.py"], dest_dir)

    assert result is not None, "without kill-switch, resolve_learnings must produce output"


def test_resolve_learnings_not_disabled_when_env_zero(tmp_path, monkeypatch):
    """AUTO_PILOT_DISABLE_LEARNINGS=0 must NOT disable injection (opt-in parse).

    Old truthy check: ``os.environ.get("AUTO_PILOT_DISABLE_LEARNINGS")`` returns
    the string "0" which is truthy → injection would be silently killed.
    New explicit check: "0" is not in {"1","true","yes","on"} → injection stays ON.
    RED: revert to the old check and this test flips to FAIL.
    """
    import unittest.mock as mock

    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    monkeypatch.setenv("AUTO_PILOT_DISABLE_LEARNINGS", "0")
    dest_dir = tmp_path / "bundle-opt-in-zero"
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        result = lr.resolve_learnings(tmp_path, ["scripts/_contract.py"], dest_dir)

    assert result is not None, (
        "=0 must NOT disable injection; only 1/true/yes/on are truthy opt-in"
    )


def test_resolve_learnings_not_disabled_when_env_false(tmp_path, monkeypatch):
    """AUTO_PILOT_DISABLE_LEARNINGS=false must NOT disable injection."""
    import unittest.mock as mock

    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    monkeypatch.setenv("AUTO_PILOT_DISABLE_LEARNINGS", "false")
    dest_dir = tmp_path / "bundle-opt-in-false"
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        result = lr.resolve_learnings(tmp_path, ["scripts/_contract.py"], dest_dir)

    assert result is not None, "=false must NOT disable injection"


def test_resolve_learnings_disabled_when_env_true(tmp_path, monkeypatch):
    """AUTO_PILOT_DISABLE_LEARNINGS=true → injection disabled."""
    import unittest.mock as mock

    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    monkeypatch.setenv("AUTO_PILOT_DISABLE_LEARNINGS", "true")
    dest_dir = tmp_path / "bundle-opt-in-true"
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        result = lr.resolve_learnings(tmp_path, ["scripts/_contract.py"], dest_dir)

    assert result is None, "=true must disable injection"


def test_resolve_learnings_disabled_when_env_yes(tmp_path, monkeypatch):
    """AUTO_PILOT_DISABLE_LEARNINGS=yes → injection disabled."""
    import unittest.mock as mock

    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(state="candidate", distinct_runs=2,
                           source_path="scripts/_contract.py")
    _write_ticket(ledger, ticket)

    monkeypatch.setenv("AUTO_PILOT_DISABLE_LEARNINGS", "yes")
    dest_dir = tmp_path / "bundle-opt-in-yes"
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        result = lr.resolve_learnings(tmp_path, ["scripts/_contract.py"], dest_dir)

    assert result is None, "=yes must disable injection"


# ---------------------------------------------------------------------------
# Integration: miner → ledger → resolver (real _apply_bump shape, not fabricated)
# ---------------------------------------------------------------------------

def test_miner_bump_to_resolver_end_to_end(tmp_path):
    """Verify that evidence written by _apply_bump is readable by _ticket_evidence_files.

    This test drives the REAL chain:
      1. Construct an Observation with source_path (as the miner does for reviewer-findings).
      2. Call bump_or_create → writes evidence in real miner shape.
      3. Load the ticket from disk via select_tickets → scope match must succeed.
      4. Call resolve_learnings → learnings.md must be written.

    Fails if miner and resolver disagree on evidence shape.
    """
    import _improvement as imp
    import unittest.mock as mock

    ledger = tmp_path / "ledger"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)

    obs = imp.Observation(
        source="reviewer-finding",
        file_basename="orchestrator.py",
        issue="worker skipped verify gate",
        candidate_asset="hook",
        run_id="run-miner-e2e-1",
        snippet='{"file":"scripts/orchestrator.py","issue":"verify skipped"}',
        source_path="scripts/orchestrator.py",
    )
    # First bump → candidate with distinct_runs=1 (below threshold)
    ticket = imp.bump_or_create(ledger, obs, repo_root=repo_root, now=now, dry_run=False)

    # Second bump from a different run_id → distinct_runs=2 → promotable
    obs2 = imp.Observation(
        source="reviewer-finding",
        file_basename="orchestrator.py",
        issue="worker skipped verify gate",
        candidate_asset="hook",
        run_id="run-miner-e2e-2",
        snippet='{"file":"scripts/orchestrator.py","issue":"verify skipped again"}',
        source_path="scripts/orchestrator.py",
    )
    ticket = imp.bump_or_create(ledger, obs2, repo_root=repo_root, now=now, dry_run=False)

    assert ticket["distinct_runs"] == 2

    # Evidence must carry source_path in the real shape
    evidence = ticket["evidence"]
    assert isinstance(evidence, list) and len(evidence) == 2
    for ev in evidence:
        assert "source_path" in ev, "miner must persist source_path in evidence"
        assert ev["source_path"] == "scripts/orchestrator.py"

    # Resolver must scope-match and write learnings.md
    dest_dir = tmp_path / "bundle"
    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        result = lr.resolve_learnings(repo_root, ["scripts/orchestrator.py"], dest_dir)

    assert result is not None, "resolver must produce learnings.md for scope-matching ticket"
    content = result.read_text()
    assert "# Injected learnings" in content
    assert "worker skipped verify gate" in content
