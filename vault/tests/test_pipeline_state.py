"""Tests for unified pipeline state file."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from pipeline import state as st  # noqa: E402


def test_load_creates_default(tmp_path: Path) -> None:
    s = st.load(tmp_path)
    assert s["schema_version"] == 1
    assert s["round"] == 0
    assert s["scores"]["structural"] is None


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    s = st.load(tmp_path)
    s["round"] = 5
    s["scores"]["structural"] = {"total": 87}
    st.save(tmp_path, s)

    s2 = st.load(tmp_path)
    assert s2["round"] == 5
    assert s2["scores"]["structural"]["total"] == 87


def test_migrate_legacy_picks_up_old_files(tmp_path: Path) -> None:
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "score-state.json").write_text(json.dumps({"total": 100}))
    (tmp_path / "meta" / "score-content-state.json").write_text(json.dumps({"total": 100}))
    (tmp_path / "meta" / "ticket-state.json").write_text(json.dumps({"tickets": {"T1": {"status": "verified"}}}))

    s = st.migrate_legacy(tmp_path)
    assert s["scores"]["structural"]["total"] == 100
    assert s["scores"]["content"]["total"] == 100
    assert "T1" in s["tickets"]
