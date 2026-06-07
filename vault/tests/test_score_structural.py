"""Characterization tests for score_structural.score_vault.

Branches covered:
- empty vault (no categories, no graph files) → all dims 0 except conflict_dup (10)
- minimal vault with one category: raw .md files, graph.json with known edges/nodes,
  concepts/entities dirs, ADRs, hot.md, wiki articles, backlinks, bases
- cross_vault branch: missing cv file → score 0
- confidence_balance band filter: all INFERRED (in-band) vs all AMBIGUOUS (out-of-band)
- conflict_dup: duplicate stems within same category → penalty
- categories loaded from meta/categories.json when present; discovered from dirs otherwise
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCORE_PATH = PLUGIN_ROOT / "scripts" / "score_structural.py"

spec = importlib.util.spec_from_file_location("score_structural", SCORE_PATH)
score_structural = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
sys.modules["score_structural"] = score_structural
spec.loader.exec_module(score_structural)  # type: ignore[union-attr]

score_vault = score_structural.score_vault


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_graph(path: Path, nodes: list, edges: list, hyperedges: list | None = None) -> None:
    data: dict = {"nodes": nodes, "links": edges}
    if hyperedges is not None:
        data["hyperedges"] = hyperedges
    path.write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# Fixture: richly-populated single-category vault (maximises most dims)
# ---------------------------------------------------------------------------

@pytest.fixture()
def rich_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    cat = vault / "cat-a"

    # categories.json present
    (vault / "meta").mkdir(parents=True)
    (vault / "meta" / "categories.json").write_text(json.dumps(["cat-a"]))

    # raw sources
    raw = cat / "raw"
    raw.mkdir(parents=True)
    for i in range(4):
        (raw / f"src-{i}.md").write_text(f"# Source {i}\ntext [[concept-x]]")

    # graph: dense, high INFERRED share, has hyperedges
    graphify_out = raw / "graphify-out"
    graphify_out.mkdir()
    nodes = [{"id": f"n{i}"} for i in range(4)]
    edges = [
        {"source": "n0", "target": "n1", "confidence": "EXTRACTED"},
        {"source": "n1", "target": "n2", "confidence": "INFERRED"},
        {"source": "n2", "target": "n3", "confidence": "INFERRED"},
        {"source": "n0", "target": "n3", "confidence": "INFERRED"},
        {"source": "n1", "target": "n3", "confidence": "INFERRED"},
        {"source": "n0", "target": "n2", "confidence": "INFERRED"},
    ]  # 6 edges / 4 nodes = density 1.5
    _write_graph(graphify_out / "graph.json", nodes, edges, hyperedges=[{"nodes": ["n0", "n1", "n2"]}])

    # wiki articles (dim 7)
    wiki = graphify_out / "wiki"
    wiki.mkdir()
    article_text = (
        "# Concept X\n\n"
        "## Source Files\n"
        "- src-0.md\n- src-1.md\n- src-2.md\n\n"
        "## Relationships\n\n- rel 1\n"
    )
    (wiki / "concept-x.md").write_text(article_text)

    # concepts + entities (dim 3)
    for sub in ("concepts", "entities"):
        subdir = cat / sub
        subdir.mkdir()
        for j in range(3):
            (subdir / f"item-{j}.md").write_text("# item")

    # decisions / ADRs (dim 4)
    dec = cat / "decisions"
    dec.mkdir()
    for j in range(2):
        (dec / f"adr-00{j}.md").write_text("# ADR")

    # hot.md (dim 6) — all 5 sections present
    (cat / "hot.md").write_text(
        "# Hot\n"
        "## God Nodes\n- x\n"
        "## Cross-bridges\n- y\n"
        "## Source Files\n- z\n"
        "## Quick Questions\n- q\n"
        "## Cross-vault\n- c\n"
    )

    # backlinks: a wiki page that links back to source pages
    sources_dir = cat / "sources"
    sources_dir.mkdir()
    (sources_dir / "source-a.md").write_text("# Source A\n")
    (sources_dir / "source-b.md").write_text("# Source B\n")
    # authored md that links back to both sources
    authored = cat / "wiki"
    authored.mkdir()
    (authored / "overview.md").write_text(
        "# Overview\n[[source-a]] [[source-b]] [[source-a]]\n"
    )

    # .base files (dim 8) — need 5
    for i in range(5):
        (vault / f"view-{i}.base").write_text("{}")

    return vault


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmptyVault:
    """Vault with zero categories (discovered, none matching) → all zeros (except conflict_dup)."""

    def test_returns_dict_shape(self, tmp_path: Path) -> None:
        vault = tmp_path / "empty"
        vault.mkdir()
        state = score_vault(vault)
        assert isinstance(state, dict)
        assert "total" in state
        assert "scores" in state
        assert "details" in state
        assert "categories" in state

    def test_all_dims_present(self, tmp_path: Path) -> None:
        vault = tmp_path / "empty"
        vault.mkdir()
        state = score_vault(vault)
        expected_dims = {
            "graph_density", "confidence_balance", "concept_entity_depth",
            "adr_pages", "cross_vault", "hot_cache", "wiki_articles",
            "bases", "backlinks", "conflict_dup",
        }
        assert set(state["scores"].keys()) == expected_dims

    def test_graph_density_zero_density_but_hyperedge_bonus(self, tmp_path: Path) -> None:
        """Empty vault: density=0 → 0 pts; hyperedge_cats==len(CATS)==0 (0==0 True) → +5.
        This is current behavior — 5.0, not 0, because 0==0 evaluates as full hyperedge score."""
        vault = tmp_path / "empty"
        vault.mkdir()
        state = score_vault(vault)
        assert state["scores"]["graph_density"] == 5.0

    def test_conflict_dup_full_score_when_no_dups(self, tmp_path: Path) -> None:
        """No spurious dups → conflict_dup = 10."""
        vault = tmp_path / "empty"
        vault.mkdir()
        state = score_vault(vault)
        assert state["scores"]["conflict_dup"] == 10

    def test_total_is_numeric(self, tmp_path: Path) -> None:
        vault = tmp_path / "empty"
        vault.mkdir()
        state = score_vault(vault)
        assert isinstance(state["total"], float | int)
        assert 0 <= state["total"] <= 100

    def test_categories_loaded_from_json(self, tmp_path: Path) -> None:
        vault = tmp_path / "cats"
        (vault / "meta").mkdir(parents=True)
        (vault / "meta" / "categories.json").write_text(json.dumps(["cat-x", "cat-y"]))
        vault.mkdir(exist_ok=True)
        state = score_vault(vault)
        assert state["categories"] == ["cat-x", "cat-y"]

    def test_categories_discovered_from_dirs(self, tmp_path: Path) -> None:
        vault = tmp_path / "disc"
        (vault / "cat-z" / "raw").mkdir(parents=True)
        state = score_vault(vault)
        assert "cat-z" in state["categories"]


class TestRichVault:
    """Single well-populated category exercises every scoring branch."""

    def test_graph_density_positive(self, rich_vault: Path) -> None:
        state = score_vault(rich_vault)
        # density = 6/4 = 1.5 → full 10 + hyperedge full 5 → 15
        assert state["scores"]["graph_density"] == 15.0

    def test_confidence_balance_high_inferred_share_out_of_band(self, rich_vault: Path) -> None:
        # EXTRACTED=1/6≈0.17, INFERRED=5/6≈0.83 → inf > 0.80 → NOT in band
        # (0.83 > 0.80 upper bound)
        state = score_vault(rich_vault)
        # 1 category, 0 in-band → 0.0
        assert state["scores"]["confidence_balance"] == 0.0

    def test_concept_entity_depth_full(self, rich_vault: Path) -> None:
        state = score_vault(rich_vault)
        assert state["scores"]["concept_entity_depth"] == 10.0

    def test_adr_pages_single_category_partial(self, rich_vault: Path) -> None:
        state = score_vault(rich_vault)
        # 1 cat with ≥2 ADRs → min(10, 10 * 1/3) = 3.3
        assert state["scores"]["adr_pages"] == pytest.approx(3.3, abs=0.1)

    def test_cross_vault_zero_when_missing(self, rich_vault: Path) -> None:
        state = score_vault(rich_vault)
        assert state["scores"]["cross_vault"] == 0
        assert "missing" in state["details"]["cross_vault"]

    def test_hot_cache_full(self, rich_vault: Path) -> None:
        state = score_vault(rich_vault)
        assert state["scores"]["hot_cache"] == 10.0

    def test_wiki_articles_full(self, rich_vault: Path) -> None:
        state = score_vault(rich_vault)
        assert state["scores"]["wiki_articles"] == 10.0

    def test_bases_full(self, rich_vault: Path) -> None:
        state = score_vault(rich_vault)
        assert state["scores"]["bases"] == 5.0

    def test_backlinks_half_coverage_when_one_source_is_weak(self, rich_vault: Path) -> None:
        # source-a has 2 inbound links, source-b has 1 → source-b weak
        state = score_vault(rich_vault)
        # source-b only has 1 inbound → weak; source-a has 2 → ok
        assert state["scores"]["backlinks"] == pytest.approx(5.0, abs=0.5)

    def test_conflict_dup_has_penalty(self, rich_vault: Path) -> None:
        """rich_vault has item-0/1/2 in both concepts/ and entities/ within cat-a.
        Scorer counts cross-subdir same-stem files as dups → 3 spurious dups → score 7.0."""
        state = score_vault(rich_vault)
        assert state["scores"]["conflict_dup"] == 7.0

    def test_total_bounded(self, rich_vault: Path) -> None:
        state = score_vault(rich_vault)
        assert 0 <= state["total"] <= 100


class TestConfidenceBalance:
    """Verify in-band logic: ext≥0.10, 0.40≤inf≤0.80, amb≤0.15."""

    def _make_vault_with_edges(self, tmp_path: Path, edges: list) -> Path:
        vault = tmp_path / "v"
        cat = vault / "cat-a"
        (vault / "meta").mkdir(parents=True)
        (vault / "meta" / "categories.json").write_text(json.dumps(["cat-a"]))
        raw = cat / "raw"
        raw.mkdir(parents=True)
        graphify_out = raw / "graphify-out"
        graphify_out.mkdir()
        nodes = [{"id": "n0"}, {"id": "n1"}]
        _write_graph(graphify_out / "graph.json", nodes, edges)
        return vault

    def test_in_band_edges_score_full(self, tmp_path: Path) -> None:
        edges = (
            [{"source": "n0", "target": "n1", "confidence": "EXTRACTED"}] * 2
            + [{"source": "n0", "target": "n1", "confidence": "INFERRED"}] * 7
            + [{"source": "n0", "target": "n1", "confidence": "AMBIGUOUS"}] * 1
        )  # ext=0.2, inf=0.7, amb=0.1 → in-band
        vault = self._make_vault_with_edges(tmp_path, edges)
        state = score_vault(vault)
        assert state["scores"]["confidence_balance"] == 10.0

    def test_all_ambiguous_out_of_band(self, tmp_path: Path) -> None:
        edges = [{"source": "n0", "target": "n1", "confidence": "AMBIGUOUS"}] * 5
        vault = self._make_vault_with_edges(tmp_path, edges)
        state = score_vault(vault)
        assert state["scores"]["confidence_balance"] == 0.0


class TestConflictDup:
    """Duplicate stems within a category reduce conflict_dup score."""

    def test_single_dup_reduces_score(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        (vault / "meta").mkdir(parents=True)
        (vault / "meta" / "categories.json").write_text(json.dumps(["cat-a"]))
        cat = vault / "cat-a" / "concepts"
        cat.mkdir(parents=True)
        # same stem twice in cat-a
        (cat / "thing.md").write_text("# a")
        sub2 = vault / "cat-a" / "entities"
        sub2.mkdir(parents=True)
        (sub2 / "thing.md").write_text("# b")  # duplicate stem within cat-a
        state = score_vault(vault)
        assert state["scores"]["conflict_dup"] == 9.0  # 10 - 1 dup

    def test_scaffolding_stems_ignored(self, tmp_path: Path) -> None:
        vault = tmp_path / "v"
        (vault / "meta").mkdir(parents=True)
        (vault / "meta" / "categories.json").write_text(json.dumps(["cat-a"]))
        cat = vault / "cat-a" / "concepts"
        cat.mkdir(parents=True)
        (cat / "hot.md").write_text("# hot")
        sub2 = vault / "cat-a" / "entities"
        sub2.mkdir(parents=True)
        (sub2 / "hot.md").write_text("# hot")  # scaffolding dup — should be ignored
        state = score_vault(vault)
        assert state["scores"]["conflict_dup"] == 10.0
