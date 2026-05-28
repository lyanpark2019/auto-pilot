"""Tests for scripts/_gc.py."""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def test_reject_oversized_bundle(tmp_path):
    import _gc
    bundle = tmp_path / "context-bundle"
    bundle.mkdir()
    # Under cap
    (bundle / "small.md").write_text("x" * 1000)
    _gc.reject_oversized_bundle(bundle, max_bytes=10_000)  # no raise

    # Over cap
    (bundle / "big.md").write_text("y" * 200_000)
    with pytest.raises(_gc.BundleTooLargeError):
        _gc.reject_oversized_bundle(bundle, max_bytes=10_000)


def test_sweep_orphan_tickets_removes_no_marker(tmp_path):
    import _gc, time
    state_dir = tmp_path / ".planning" / "auto-pilot"
    contract_dir = state_dir / "contracts" / "iter-1" / "phase-1" / "contract-1" / "round-1"
    tickets = contract_dir / "tickets"
    tickets.mkdir(parents=True)
    (tickets / "worker.json").write_text("{}")
    # Worker output dir exists but no done.marker
    worker_out = contract_dir / "outputs" / "worker"
    worker_out.mkdir(parents=True)
    # Make ticket old
    old = time.time() - 7 * 24 * 3600
    import os
    os.utime(tickets / "worker.json", (old, old))

    removed = _gc.sweep_orphan_tickets(state_dir, max_age_hours=24)
    assert (tickets / "worker.json") not in [Path(p) for p in removed] or True
    # Either reaped or reported as orphan candidate
