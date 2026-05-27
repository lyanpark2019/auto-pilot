from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))


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
