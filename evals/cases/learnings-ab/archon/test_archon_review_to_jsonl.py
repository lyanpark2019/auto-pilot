#!/usr/bin/env python3
"""End-to-end + drift test for archon_review_to_jsonl.py.

Run: python3 .archon/scripts/test_archon_review_to_jsonl.py
(pure-stdlib script-style; no pytest dependency on the Archon host).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ADAPTER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ADAPTER_DIR))
import archon_review_to_jsonl as adapter  # noqa: E402

# auto-pilot scripts/ — the durable Python the adapter feeds (live miner + vocab).
AUTO_PILOT_SCRIPTS = Path("/Users/lyan/Documents/Project/auto-pilot/scripts")


def _load_auto_pilot_module(name: str):
    """Import an auto-pilot scripts/*.py module by absolute path."""
    sys.path.insert(0, str(AUTO_PILOT_SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, AUTO_PILOT_SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_vocab_drift() -> None:
    """The frozen inline copy must equal the live learning_miner list (16 items)."""
    miner = _load_auto_pilot_module("learning_miner")
    assert adapter.REVIEWER_FINDING_CLASSES == miner.REVIEWER_FINDING_CLASSES, (
        "frozen REVIEWER_FINDING_CLASSES drifted from learning_miner.py:58-66"
    )
    assert len(adapter.REVIEWER_FINDING_CLASSES) == 16
    print("OK test_vocab_drift")


def _review() -> dict:
    return {
        "reviewer": "claude",
        "verdict": "REJECT",
        "findings": [
            {"severity": "P1", "title": "loop bound includes len",
             "detail": "iterates one past end", "file": "x.py", "class": "off-by-one"},
            {"severity": "P2", "title": "cosmetic naming",
             "detail": "rename foo", "file": "y.py", "class": "doc-drift"},
        ],
    }


def test_adapter_e2e() -> None:
    miner = _load_auto_pilot_module("learning_miner")
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        review_path = repo / "review.json"
        review_path.write_text(json.dumps(_review()))
        os.environ["RUN_ID"] = "run-A"

        rc = adapter.main([str(review_path), str(repo)])
        assert rc == 0
        jsonl = repo / adapter.JSONL_REL
        lines = [json.loads(x) for x in jsonl.read_text().splitlines() if x.strip()]

        # exactly one line: P1 kept, P2 dropped
        assert len(lines) == 1, f"expected 1 line, got {lines}"
        line = lines[0]
        assert line == {
            "file": "x.py", "issue": "loop bound includes len",
            "candidate_asset": None, "run_id": "run-A", "class": "off-by-one",
        }, line
        print("OK test_adapter_e2e: exactly one P1 line, P2 dropped")

        # re-run → ZERO new lines (canon_key dedupe)
        adapter.main([str(review_path), str(repo)])
        lines2 = [x for x in jsonl.read_text().splitlines() if x.strip()]
        assert len(lines2) == 1, f"dedupe failed, got {len(lines2)} lines"
        print("OK dedupe: re-run appended zero lines")

        # REAL miner scan over the produced JSONL → exactly one Observation,
        # fingerprint keyed on the controlled-vocab class ('off-by-one').
        obs = miner.scan_reviewer_findings(repo, "run-A")
        assert len(obs) == 1, f"expected 1 Observation, got {obs}"
        assert obs[0].source == "reviewer-finding"
        assert obs[0].issue == "off-by-one"  # keyed on class, not the title prose
        assert obs[0].run_id == "run-A"
        print("OK real miner: one Observation, fingerprint keyed on class")

        # REAL learning_miner end-to-end → a PHYSICAL ledger file is written.
        # Non-dry-run gate needs state.json run_id; commit-to pins a temp ledger.
        imp = _load_auto_pilot_module("_improvement")
        (repo / ".planning" / "auto-pilot").mkdir(parents=True, exist_ok=True)
        (repo / ".planning" / "auto-pilot" / "state.json").write_text(
            json.dumps({"run_id": "run-A"})
        )
        ledger = repo / "ledger"
        from datetime import datetime, timezone
        result = miner.run_miner(
            repo, commit_to=ledger, now=datetime.now(timezone.utc), dry_run=False
        )
        assert result["candidates"] >= 1, result
        ledger_files = list(ledger.glob("*.json"))
        assert ledger_files, "no physical ledger file written"
        ticket = json.loads(ledger_files[0].read_text())
        fp = imp.compute_fingerprint("reviewer-finding", "x.py", "off-by-one", "")
        assert ticket["fingerprint"] == fp, (ticket["fingerprint"], fp)
        assert ticket["distinct_runs"] == 1, ticket
        print(f"OK ledger: physical file {ledger_files[0].name} fp={fp[:12]}.. distinct_runs=1")


if __name__ == "__main__":
    test_vocab_drift()
    test_adapter_e2e()
    print("\nALL PASS")
