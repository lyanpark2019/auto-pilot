"""pytest fixtures for notebooklm-vault-builder."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))


@pytest.fixture
def fake_vault(tmp_path: Path) -> Path:
    """Minimal valid vault fixture for scoring + ticket tests."""
    vault = tmp_path / "vault"
    (vault / "meta").mkdir(parents=True)
    (vault / "meta" / "categories.json").write_text(json.dumps(["cat-a", "cat-b"]))
    (vault / "meta" / "score-state.json").write_text(json.dumps({
        "total": 95.0,
        "scores": {"graph_density": 14, "confidence_balance": 9.0, "wiki_articles": 10},
    }))
    (vault / "meta" / "score-content-state.json").write_text(json.dumps({
        "total": 88.0,
        "scores": {"edge_fact": 25, "concept_accuracy": 18},
    }))
    for cat in ("cat-a", "cat-b"):
        (vault / cat / "raw").mkdir(parents=True)
        (vault / cat / "raw" / "_index.md").write_text("# index")
    return vault
