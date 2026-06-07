from __future__ import annotations

import json
import re
from pathlib import Path


DOCS_README = Path("docs/README.md")
ONBOARDING = Path("docs/onboarding/README.md")
DOC_MANAGEMENT_REFERENCE = Path("skills/doc-management/references/onboarding-hub.md")
DOC_MANAGEMENT_SKILL = Path("skills/doc-management/SKILL.md")
ROOT_README = Path("README.md")
CLAUDE = Path("CLAUDE.md")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_onboarding_docs_entrypoints_exist() -> None:
    assert DOCS_README.exists()
    assert ONBOARDING.exists()
    assert DOC_MANAGEMENT_REFERENCE.exists()


def test_docs_readme_routes_humans_and_agents_to_onboarding_hub() -> None:
    text = _read(DOCS_README)

    assert "docs/onboarding/README.md" in text
    assert "Developer" in text
    assert "AI agent" in text
    assert "source-of-truth" in text
    assert "docs/plans/" in text


def test_onboarding_hub_requires_graphify_before_source_scanning() -> None:
    text = _read(ONBOARDING)

    assert "graphify update . --force" in text
    assert "graphify query" in text
    assert "graphify explain" in text
    assert "graphify path" in text
    assert "graphify affected" in text
    assert "What" in text
    assert "Why" in text


def test_doc_management_owns_reusable_onboarding_hub_workflow() -> None:
    reference = _read(DOC_MANAGEMENT_REFERENCE)
    skill = _read(DOC_MANAGEMENT_SKILL)

    assert "AI / Developer onboarding hub" in reference
    assert "Case A" in reference
    assert "Case B" in reference
    assert "graphify extract . --mode deep" in reference
    assert "graphify update . --force" in reference
    assert "onboarding-hub.md" in skill


def test_root_entrypoints_link_to_onboarding_hub() -> None:
    readme = _read(ROOT_README)
    claude = _read(CLAUDE)

    assert "docs/onboarding/README.md" in readme
    assert "docs/onboarding/README.md" in claude


def test_doc_management_references_use_current_graphify_cli() -> None:
    docs = "\n".join(path.read_text(encoding="utf-8") for path in Path("skills/doc-management").rglob("*.md"))

    assert not re.search(r"graphify update \.(?! --force)", docs)
    assert "graphify update --force" not in docs
    assert "`graphify .`" not in docs


def test_onboarding_hub_includes_persistent_llm_wiki_pattern() -> None:
    combined = _read(ONBOARDING) + "\n" + _read(DOC_MANAGEMENT_REFERENCE)

    assert "persistent, compounding wiki" in combined
    assert "Raw sources" in combined
    assert "Generated wiki" in combined
    assert "Schema" in combined
    assert "Ingest" in combined
    assert "Query" in combined
    assert "Lint" in combined
    assert "index.md" in combined
    assert "log.md" in combined


def test_onboarding_graphify_examples_are_known_good_queries() -> None:
    text = _read(ONBOARDING)
    manifest = json.loads(Path("scripts/graphify_query_suite.json").read_text(encoding="utf-8"))
    commands = {" ".join(test["cmd"]) for test in manifest["tests"]}

    assert "auto-pilot PM worker reviewer state worktree contract schema hooks" not in text
    assert 'graphify affected "WorktreeManager"' not in text
    assert "graphify query WorktreeManager apply_to_main collect_patches cleanup main_apply_lock --graph graphify-out/graph.json --budget 1400" in commands
    assert "graphify query collect_round_outcome read_review done marker schema validate --graph graphify-out/graph.json --budget 1400" in commands
    assert "graphify affected \"collect_round_outcome()\"" in text
