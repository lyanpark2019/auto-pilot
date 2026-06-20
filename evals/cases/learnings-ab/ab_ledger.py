"""Frozen-ledger lifecycle for the learning-loop A/B driver (Task 10).

Split out of ``archon_ab_driver.py`` to keep both files within the 500-line
budget.  Owns the three concerns around the durable Hermes ledger that the A/B
depends on:

  - ``seed_frozen_ledger`` — seed a stage-A ledger ONCE via the REAL CAPTURE
    adapter + miner path (``--run-id``) so a recurring class reaches
    ``distinct_runs>=2`` and is gate-passed.  No hand-built tickets: the real
    pipeline stamps provenance, so ``_learnings.select_tickets`` accepts them.
  - ``ledger_sha`` — order-stable SHA-256 over every ticket file, the
    train/test-split assertion's witness (codex P0-3).
  - ``copy_ledger`` — per-arm COPY so scoring never mutates the frozen original.

``_seed_env`` threads the REAL user site-packages onto a child ``PYTHONPATH`` so
the miner imports ``referencing`` even when a test has monkeypatched HOME to an
empty temp dir (r1-phrasing memory gotcha).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import site
import subprocess
import sys
from pathlib import Path
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_ADAPTER = _THIS_DIR / "archon" / "archon_review_to_jsonl.py"

# Resolve the REAL user site-packages ONCE, at import — before any test
# monkeypatches HOME.  ``referencing`` (a jsonschema dependency the miner
# imports) lives in the HOME-derived user site-packages.
try:
    _USER_SITE: str = site.getusersitepackages()
except Exception:  # pragma: no cover - site API never raises in practice
    _USER_SITE = ""


def _seed_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Child-process env that survives a test HOME override.

    Prepends ``scripts/`` and the REAL user site-packages onto PYTHONPATH so the
    miner imports ``_improvement``/``jsonschema``/``referencing`` even when the
    parent test has monkeypatched HOME to an empty temp dir.
    """
    env = dict(os.environ)
    parts = [str(_SCRIPTS)]
    if _USER_SITE:
        parts.append(_USER_SITE)
    existing = env.get("PYTHONPATH", "")
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    if extra:
        env.update(extra)
    return env


def _run_adapter(review: dict[str, Any], repo_root: Path, run_id: str) -> None:
    """Write a review.json then run the real CAPTURE adapter into repo_root."""
    review_path = repo_root / "_seed_review.json"
    review_path.write_text(json.dumps(review))
    subprocess.run(
        [sys.executable, str(_ADAPTER), str(review_path), str(repo_root)],
        check=True, capture_output=True, text=True,
        env=_seed_env({"RUN_ID": run_id}),
    )
    review_path.unlink()


def _run_miner(repo_root: Path, ledger_dir: Path, run_id: str) -> dict[str, Any]:
    """Run the REAL miner via --run-id; return its parsed JSON verdict line."""
    env = _seed_env()
    proc = subprocess.run(
        [
            sys.executable, str(_SCRIPTS / "learning_miner.py"),
            "--repo-root", str(repo_root),
            "--commit-to", str(ledger_dir),
            "--run-id", run_id,
            "--json",
        ],
        check=True, capture_output=True, text=True, env=env,
    )
    parsed = json.loads(proc.stdout.strip().splitlines()[-1])
    if not isinstance(parsed, dict):
        raise AssertionError(f"miner emitted non-object verdict: {parsed!r}")
    return parsed


def seed_frozen_ledger(
    repo_root: Path,
    ledger_dir: Path,
    *,
    defect_class: str,
    defect_file: str,
    run_ids: tuple[str, str] = ("seedA-1", "seedA-2"),
) -> dict[str, Any]:
    """Seed a FROZEN stage-A ledger via the real adapter+miner, ONCE.

    Captures the SAME ``defect_class`` at ``defect_file`` under two DISTINCT
    run_ids so the ticket reaches ``distinct_runs==2`` and is gate-passed.
    Returns the miner's final JSON verdict (asserts ``promotable_count>=1``).
    """
    ledger_dir.mkdir(parents=True, exist_ok=True)
    last: dict[str, Any] = {}
    for rid in run_ids:
        review = {
            "reviewer": "claude",
            "verdict": "REJECT",
            "findings": [
                {
                    "severity": "P1",
                    "title": f"recurring {defect_class}",
                    "detail": "seed",
                    "file": defect_file,
                    "class": defect_class,
                }
            ],
        }
        _run_adapter(review, repo_root, rid)
        last = _run_miner(repo_root, ledger_dir, rid)
    if last.get("promotable_count", 0) < 1:
        raise AssertionError(
            f"seed ledger not promotable: {last!r} (need distinct_runs>=2)"
        )
    return last


def ledger_sha(ledger_dir: Path) -> str:
    """Order-stable SHA-256 over every ticket file's bytes in a ledger dir.

    Lock/temp files are ignored; only ``*.json`` ticket payloads count, sorted
    by name so the digest is independent of filesystem enumeration order.
    """
    h = hashlib.sha256()
    for path in sorted(ledger_dir.glob("*.json")):
        h.update(path.name.encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def copy_ledger(frozen: Path, dest: Path) -> Path:
    """Per-arm COPY of the frozen ledger (ticket files only)."""
    dest.mkdir(parents=True, exist_ok=True)
    for path in frozen.glob("*.json"):
        shutil.copy2(path, dest / path.name)
    return dest
