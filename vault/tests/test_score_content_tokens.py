"""Regression test: CJK token filter must not drop 2-char Korean tokens.

Bug: original score_content.py used `len(w) > 2` which dropped all 2-char Korean
words ("한국", "로또", "시장"). Korean labels with only 2-char tokens produced
empty token list → edge marked as fail even when grounded.

Fix: separate length thresholds — CJK ≥ 2, ASCII > 2.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCORE_PATH = PLUGIN_ROOT / "scripts" / "score_content.py"

spec = importlib.util.spec_from_file_location("score_content", SCORE_PATH)
score_content = importlib.util.module_from_spec(spec)
sys.modules["score_content"] = score_content
spec.loader.exec_module(score_content)


def test_cjk_two_char_tokens_pass(tmp_path: Path) -> None:
    """2-char Korean tokens must be retained (the regression we fixed)."""
    vault = tmp_path / "v"
    cat = vault / "cat-a"
    (cat / "raw").mkdir(parents=True)
    (cat / "raw" / "src.md").write_text("한국 로또 시장 분석")
    graphify_out = cat / "raw" / "graphify-out"
    graphify_out.mkdir()
    import json
    (graphify_out / "graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "n1", "label": "한국 로또 시장"},
            {"id": "n2", "label": "시장 분석"},
        ],
        "links": [
            {"source": "n1", "target": "n2", "confidence": "INFERRED"},
        ],
    }))

    passed, total, failed = score_content.edge_token_check(vault, ["cat-a"], sample_n=10)
    assert total == 1
    assert passed == 1, f"2-char Korean tokens should pass; failed={failed}"


def test_ascii_short_tokens_still_filtered(tmp_path: Path) -> None:
    """ASCII tokens ≤ 2 chars still get filtered (noise prevention)."""
    vault = tmp_path / "v"
    cat = vault / "cat-a"
    (cat / "raw").mkdir(parents=True)
    (cat / "raw" / "src.md").write_text("aa bb cc")
    graphify_out = cat / "raw" / "graphify-out"
    graphify_out.mkdir()
    import json
    (graphify_out / "graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "n1", "label": "aa"},
            {"id": "n2", "label": "bb"},
        ],
        "links": [{"source": "n1", "target": "n2", "confidence": "INFERRED"}],
    }))

    passed, total, _ = score_content.edge_token_check(vault, ["cat-a"], sample_n=10)
    assert total == 1
    # both labels filtered to empty tokens → cannot verify → fail
    assert passed == 0


def test_mixed_label_uses_longer_token(tmp_path: Path) -> None:
    """Label like '로또잭팟 (QR코드 당첨확인, App Store)' should split + match real tokens."""
    vault = tmp_path / "v"
    cat = vault / "cat-a"
    (cat / "raw").mkdir(parents=True)
    (cat / "raw" / "src.md").write_text("로또잭팟 앱 출시 당첨확인 기능 포함")
    graphify_out = cat / "raw" / "graphify-out"
    graphify_out.mkdir()
    import json
    (graphify_out / "graph.json").write_text(json.dumps({
        "nodes": [
            {"id": "n1", "label": "로또잭팟 (QR코드 당첨확인, App Store)"},
            {"id": "n2", "label": "당첨확인"},
        ],
        "links": [{"source": "n1", "target": "n2", "confidence": "AMBIGUOUS"}],
    }))

    passed, total, _ = score_content.edge_token_check(vault, ["cat-a"], sample_n=10)
    assert passed == 1
