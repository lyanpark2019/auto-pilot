from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


# ---------------------------------------------------------------------------
# Shared ledger helpers — available to test_ledger.py and test_rebalance.py
# ---------------------------------------------------------------------------

def seed_ledger() -> dict[str, Any]:
    # Minimal valid ledger matching schemas/routing-ledger.schema.json.
    return {
        "schema_version": 1,
        "assignments": {},
        "records": [],
        "rebalance_log": [],
    }


def ledger_record(
    task_id: str = "t1",
    role: str = "worker-primary",
    task_class: str = "feature-multi-file",
    model: str = "sonnet",
    gates_first_try: bool = True,
    review_rounds: int = 1,
    rejects_real: int = 0,
    p0_escaped: bool | None = None,
    ts: str = "2026-06-12T00:00:00+00:00",
) -> dict[str, Any]:
    # Build a minimal ledger record with the given outcome fields.
    outcome: dict[str, Any] = {
        "gates_first_try": gates_first_try,
        "review_rounds": review_rounds,
        "rejects_real": rejects_real,
    }
    if p0_escaped is not None:
        outcome["p0_escaped"] = p0_escaped
    return {
        "ts": ts,
        "task_id": task_id,
        "role": role,
        "task_class": task_class,
        "model": model,
        "outcome": outcome,
    }


@pytest.fixture()
def in_tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


@pytest.fixture()
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def hooks_dir(repo_root) -> Path:
    return repo_root / "hooks"


@pytest.fixture()
def sample_spec(tmp_path) -> Path:
    spec = tmp_path / "spec.md"
    spec.write_text(
        "# Spec\n\n"
        "## Phase 1: setup\n"
        "intro\n\n"
        "## Phase 2: build\n"
        "more\n\n"
        "## Phase 3: ship\n"
    )
    return spec


@pytest.fixture()
def clean_env(monkeypatch):
    for var in ("AUTO_PILOT_FORCE_COMPOSITION_ROOT", "AUTO_PILOT_BASH_BYPASS"):
        monkeypatch.delenv(var, raising=False)
    yield
