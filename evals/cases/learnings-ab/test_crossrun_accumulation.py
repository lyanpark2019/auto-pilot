"""Cross-run accumulation integration test (Task 7) — NO Archon.

Simulates TWO separate Archon runs *without* Archon: for each of TWO stage-A
diffs of the SAME defect class, run the REAL adapter
(``archon/archon_review_to_jsonl.py``) over a synthetic REJECT ``review.json``
carrying a DISTINCT ``run_id``, then the REAL miner
(``learning_miner.run_miner`` with ``run_id=...``) committing to one shared tmp
ledger dir (``commit_to`` + a pinned ``repo_root`` so both runs resolve the
SAME ticket file).

Asserts:
  * ``distinct_runs`` climbs 1 -> 2 across the two runs and the ticket becomes
    ``is_promotable`` (reviewer-finding threshold = 2);
  * IDEMPOTENCE: re-running run-2's SAME diff with the SAME ``run_id`` leaves
    ``distinct_runs`` at 2 (the anti-d1-inflation regression — a persisted line
    re-mined under its own run_id must not accrue a fresh distinct run);
  * two DIFFERENT ``repo_root`` paths resolve to DIFFERENT
    ``_improvement.project_slug`` and DIFFERENT default ledger dirs (documents the
    worktree-divergence hazard the YAML ``worktree.enabled: false`` fix addresses).

Deterministic: a fixed injected ``now``; no ``datetime.now()`` / ``random`` in
any asserted path. ``run_id`` is supplied explicitly, never derived from a clock.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Callable, cast

import pytest

_THIS_DIR = Path(__file__).resolve().parent
# evals/cases/learnings-ab -> repo root is three levels up.
_REPO_ROOT = _THIS_DIR.parents[2]
_ARCHON_DIR = _THIS_DIR / "archon"
_SCRIPTS = _REPO_ROOT / "scripts"

# scripts/ first so the adapter's lazy ``import learning_miner`` (which itself
# does ``import _improvement``) resolves the live auto-pilot modules.
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_ARCHON_DIR))

import archon_review_to_jsonl as adapter  # noqa: E402

# A frozen, clock-independent timestamp so the test is byte-deterministic.
_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)

# The single defect class shared by BOTH stage-A diffs (same file basename so the
# fingerprint collapses to ONE ticket; only the run_id differs run-to-run).
_DEFECT_CLASS = "off-by-one"
_DEFECT_FILE = "stage_a.py"


def _load_module(name: str, path: Path) -> ModuleType:
    """Import a module by absolute path (mirrors archon/test_archon_review_to_jsonl)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


miner = _load_module("learning_miner", _SCRIPTS / "learning_miner.py")
imp = _load_module("_improvement", _SCRIPTS / "_improvement.py")


def _reject_review(run_label: str) -> dict[str, object]:
    """A REJECT review.json with ONE P1 off-by-one finding on the shared file.

    ``run_label`` varies only the prose title (a real later diff phrases the same
    class differently) — the fingerprint keys on ``class``, so both still collapse
    to one ticket; distinct_runs accrues only on the differing run_id.
    """
    return {
        "reviewer": "claude",
        "verdict": "REJECT",
        "findings": [
            {
                "severity": "P1",
                "title": f"loop bound includes len ({run_label})",
                "detail": "iterates one past the end of the sequence",
                "file": _DEFECT_FILE,
                "class": _DEFECT_CLASS,
            }
        ],
    }


def _run_one(repo: Path, ledger: Path, run_id: str, run_label: str) -> dict[str, object]:
    """One simulated Archon run: adapter (capture) then miner (mine, persist).

    ``repo`` is the pinned canonical repo-root (stable across runs so the home
    ledger slug would be identical); ``ledger`` is the shared ``commit_to`` dir
    both runs write to. Returns the miner's verdict JSON dict.
    """
    review_path = repo / f"review-{run_id}.json"
    review_path.write_text(json.dumps(_reject_review(run_label)))

    # CAPTURE: adapter reads RUN_ID from the env (its only run_id source).
    rc = adapter.main([str(review_path), str(repo)])
    assert rc == 0

    # MINE: explicit --run-id satisfies the non-dry-run gate without state.json.
    result = miner.run_miner(
        repo,
        commit_to=ledger,
        now=_NOW,
        dry_run=False,
        run_id=run_id,
    )
    return cast("dict[str, object]", result)


def _ticket_file(ledger: Path) -> Path:
    files = list(ledger.glob("*.json"))
    assert len(files) == 1, f"expected exactly one ticket, got {[f.name for f in files]}"
    return files[0]


@pytest.fixture()
def env_run_id(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Set the adapter's RUN_ID env per call; restored automatically by monkeypatch."""

    def _set(value: str) -> None:
        monkeypatch.setenv("RUN_ID", value)

    return _set


def test_distinct_runs_climbs_to_promotable(
    tmp_path: Path, env_run_id: Callable[[str], None]
) -> None:
    """Two stage-A diffs, same class, DISTINCT run_ids -> distinct_runs 1->2, promotable."""
    repo = tmp_path / "repo"
    (repo / ".planning" / "auto-pilot").mkdir(parents=True)
    ledger = tmp_path / "ledger"

    # --- Run 1 (run_id = run-1) ---
    env_run_id("run-1")
    r1 = _run_one(repo, ledger, "run-1", "first")
    t1 = json.loads(_ticket_file(ledger).read_text())
    assert t1["source"] == "reviewer-finding"
    assert t1["distinct_runs"] == 1, t1
    assert not miner.is_promotable(t1), "one run must not yet be promotable"
    assert r1["promotable_count"] == 0, r1

    # Fingerprint keyed on the controlled-vocab class, not the prose title.
    expected_fp = imp.compute_fingerprint(
        "reviewer-finding", _DEFECT_FILE, _DEFECT_CLASS, ""
    )
    assert t1["fingerprint"] == expected_fp, (t1["fingerprint"], expected_fp)

    # --- Run 2 (run_id = run-2, SAME class, SAME pinned repo + ledger) ---
    env_run_id("run-2")
    r2 = _run_one(repo, ledger, "run-2", "second")
    t2 = json.loads(_ticket_file(ledger).read_text())
    assert t2["fingerprint"] == expected_fp, "second run must hit the SAME ticket"
    assert t2["distinct_runs"] == 2, t2
    assert miner.is_promotable(t2), "two distinct runs of one class -> promotable"
    assert cast(int, r2["promotable_count"]) >= 1, r2
    assert r2["verdict"] == "promotable", r2

    # Evidence carries exactly the two distinct run_ids (no inflation).
    run_ids = {e["run_id"] for e in t2["evidence"]}
    assert run_ids == {"run-1", "run-2"}, run_ids


def test_idempotent_rerun_same_run_id(
    tmp_path: Path, env_run_id: Callable[[str], None]
) -> None:
    """Re-running run-2's SAME diff/run_id leaves distinct_runs at 2 (anti-d1 inflation)."""
    repo = tmp_path / "repo"
    (repo / ".planning" / "auto-pilot").mkdir(parents=True)
    ledger = tmp_path / "ledger"

    env_run_id("run-1")
    _run_one(repo, ledger, "run-1", "first")
    env_run_id("run-2")
    _run_one(repo, ledger, "run-2", "second")
    t2 = json.loads(_ticket_file(ledger).read_text())
    assert t2["distinct_runs"] == 2

    # Re-run run-2 byte-identically: SAME run_id, SAME review -> the adapter's
    # canon_key dedupe drops the JSONL line AND the miner's (run_id, snippet)
    # dedupe is idempotent -> distinct_runs stays 2.
    env_run_id("run-2")
    r3 = _run_one(repo, ledger, "run-2", "second")
    t3 = json.loads(_ticket_file(ledger).read_text())
    assert t3["distinct_runs"] == 2, ("re-run inflated distinct_runs", t3)
    assert t3["occurrences"] == 2, t3
    assert {e["run_id"] for e in t3["evidence"]} == {"run-1", "run-2"}
    assert cast(int, r3["promotable_count"]) >= 1, r3

    # The JSONL itself must not have grown (adapter canon_key dedupe).
    jsonl = repo / adapter.JSONL_REL
    n_lines = len([x for x in jsonl.read_text().splitlines() if x.strip()])
    assert n_lines == 2, f"adapter appended a duplicate line: {n_lines} lines"


def test_distinct_repo_roots_diverge_slug_and_ledger(tmp_path: Path) -> None:
    """Two DIFFERENT repo-root paths -> DIFFERENT project_slug + default ledger dir.

    Documents the worktree-divergence hazard: Archon's timestamped worktree
    isolation yields a different absolute repo path per run, so the home-ledger
    slug (which embeds that path) diverges and cross-run memory silently splits.
    The YAML ``worktree.enabled: false`` + a stable canonical ``--repo-root`` is
    the fix; this asserts the hazard is real so the fix has a regression anchor.
    """
    root_a = tmp_path / "wt-2026-06-20-aaaa"
    root_b = tmp_path / "wt-2026-06-20-bbbb"
    root_a.mkdir()
    root_b.mkdir()

    slug_a = imp.project_slug(root_a)
    slug_b = imp.project_slug(root_b)
    assert slug_a != slug_b, "distinct worktree paths must yield distinct slugs"

    # Default (home) ledger dir embeds the slug -> diverges across worktrees.
    ledger_a = imp.ledger_dir(root_a, None)
    ledger_b = imp.ledger_dir(root_b, None)
    assert ledger_a != ledger_b, "divergent slugs -> divergent home ledger dirs"
    assert slug_a in str(ledger_a) and slug_b in str(ledger_b)

    # The pinning fix: an explicit shared commit_to collapses both back to ONE
    # ledger regardless of repo-root (this is what the driver/YAML pins).
    shared = tmp_path / "pinned-ledger"
    assert imp.ledger_dir(root_a, shared) == imp.ledger_dir(root_b, shared) == shared


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
