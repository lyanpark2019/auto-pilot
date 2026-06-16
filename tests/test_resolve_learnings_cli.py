"""Tests for scripts/_resolve_learnings_cli.py.

Uses REAL schema-valid tickets seeded into a temp ledger dir.
Invokes the REAL cmd_resolve_learnings — no mocking of internals.
"""
from __future__ import annotations

import argparse
import json
import sys
import unittest.mock as mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _resolve_learnings_cli as cli  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — build schema-valid tickets (mirrors test_learnings.py shape)
# ---------------------------------------------------------------------------

def _evidence_entry(
    run_id: str = "run-1",
    snippet: str = "worker skipped verify",
    source_path: str = "",
) -> dict:
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
    """Return a schema-valid improvement ticket.

    ``state="candidate"`` + ``distinct_runs=2`` + ``source="reviewer-finding"``
    passes ``is_promotable()`` (threshold=2) — the gate-passed condition.
    Use ``distinct_runs=1`` for a sub-threshold (excluded) ticket.
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


def _make_args(
    repo_root: str = ".",
    scope_files: list | None = None,
    dest_dir: str = "/tmp/ap-rl-test",
) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.repo_root = repo_root
    ns.scope_files = scope_files if scope_files is not None else []
    ns.dest_dir = dest_dir
    return ns


# ---------------------------------------------------------------------------
# (a) No match → learnings_path null, matched 0, exit 0
# ---------------------------------------------------------------------------

def test_no_match_returns_null_matched_zero(tmp_path, capsys):
    """When no gate-passed ticket matches the scope, cmd returns ok JSON with matched=0."""
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(
        fingerprint="b" * 64,
        state="candidate",
        distinct_runs=1,  # sub-threshold → excluded by gate
        source_path="scripts/_contract.py",
    )
    _write_ticket(ledger, ticket)

    dest_dir = tmp_path / "bundle"
    args = _make_args(scope_files=["scripts/"], dest_dir=str(dest_dir))

    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        rc = cli.cmd_resolve_learnings(args)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert rc == 0
    assert output["ok"] is True
    assert output["learnings_path"] is None
    assert output["matched"] == 0
    assert not (dest_dir / "context-bundle" / "learnings.md").exists()


def test_empty_ledger_returns_null_matched_zero(tmp_path, capsys):
    """When the ledger dir is absent, cmd returns ok JSON with matched=0."""
    missing_ledger = tmp_path / "no-ledger"

    dest_dir = tmp_path / "bundle2"
    args = _make_args(scope_files=["scripts/"], dest_dir=str(dest_dir))

    with mock.patch("_learnings.ledger_dir", return_value=missing_ledger):
        rc = cli.cmd_resolve_learnings(args)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert rc == 0
    assert output["ok"] is True
    assert output["learnings_path"] is None
    assert output["matched"] == 0


# ---------------------------------------------------------------------------
# (b) Gate-passed ticket with source_path in scope → learnings_path non-null
# ---------------------------------------------------------------------------

def test_gate_passed_in_scope_writes_learnings(tmp_path, capsys):
    """A gate-passed ticket whose source_path is in scope → learnings.md written."""
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(
        fingerprint="a" * 64,
        state="candidate",
        distinct_runs=2,  # passes is_promotable threshold
        source_path="scripts/_contract.py",
    )
    _write_ticket(ledger, ticket)

    dest_dir = tmp_path / "bundle3"
    args = _make_args(scope_files=["scripts/"], dest_dir=str(dest_dir))

    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        rc = cli.cmd_resolve_learnings(args)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert rc == 0
    assert output["ok"] is True
    assert output["matched"] == 1
    assert output["learnings_path"] is not None

    learnings_file = Path(output["learnings_path"])
    assert learnings_file.exists()
    assert learnings_file == dest_dir / "context-bundle" / "learnings.md"
    content = learnings_file.read_text()
    assert "Injected learnings" in content


def test_gate_passed_promoted_state_writes_learnings(tmp_path, capsys):
    """A ticket with state=promoted always passes the gate → learnings.md written."""
    ledger = tmp_path / "ledger"
    ticket = _valid_ticket(
        fingerprint="c" * 64,
        state="promoted",
        distinct_runs=1,  # threshold irrelevant for state=promoted
        source_path="scripts/_contract.py",
    )
    _write_ticket(ledger, ticket)

    dest_dir = tmp_path / "bundle4"
    args = _make_args(scope_files=["scripts/"], dest_dir=str(dest_dir))

    with mock.patch("_learnings.ledger_dir", return_value=ledger):
        rc = cli.cmd_resolve_learnings(args)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())

    assert rc == 0
    assert output["matched"] == 1
    assert output["learnings_path"] is not None


# ---------------------------------------------------------------------------
# (c) register_cli_subparsers wires resolve-learnings onto a sub-parser group
# ---------------------------------------------------------------------------

def test_register_cli_subparsers_registers_command():
    """register_cli_subparsers adds a resolve-learnings parser with required args."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    cli.register_cli_subparsers(sub)

    args = parser.parse_args([
        "resolve-learnings",
        "--repo-root", "/tmp/repo",
        "--scope", "scripts/",
        "--dest-dir", "/tmp/dest",
    ])

    assert args.repo_root == "/tmp/repo"
    assert args.scope_files == ["scripts/"]
    assert args.dest_dir == "/tmp/dest"
    assert args.func is cli.cmd_resolve_learnings


def test_register_cli_subparsers_scope_repeatable():
    """--scope can be supplied multiple times."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    cli.register_cli_subparsers(sub)

    args = parser.parse_args([
        "resolve-learnings",
        "--scope", "scripts/",
        "--scope", "hooks/",
        "--dest-dir", "/tmp/dest",
    ])

    assert args.scope_files == ["scripts/", "hooks/"]
