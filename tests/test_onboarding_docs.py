from __future__ import annotations

import json
import re
from pathlib import Path


DOCS_README = Path("docs/README.md")
ONBOARDING = Path("docs/onboarding/README.md")
DOC_MANAGEMENT_REFERENCE = Path("skills/doc-management/references/onboarding-hub.md")
DOC_MANAGEMENT_SKILL = Path("skills/doc-management/SKILL.md")
PROJECT_CONTEXT = Path("skills/auto-pilot/references/project-context-resolution.md")
VAULT_BUILD = Path("commands/vault-build.md")
VAULT_EXPORT = Path("vault/pipeline/export.py")
ROOT_README = Path("README.md")
CLAUDE = Path("CLAUDE.md")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _frontmatter(path: Path) -> dict[str, str]:
    text = _read(path)
    if not text.startswith("---\n"):
        return {}
    block = text.split("\n---\n", 1)[0].removeprefix("---\n")
    return {key.strip(): value.strip() for key, _, value in (line.partition(":") for line in block.splitlines())}


def test_onboarding_docs_entrypoints_exist() -> None:
    assert DOCS_README.exists()
    assert ONBOARDING.exists()
    assert DOC_MANAGEMENT_REFERENCE.exists()


def test_onboarding_docs_carry_freshness_frontmatter() -> None:
    required = {"type", "topic", "source_commit", "manual_edit"}

    for path in (DOCS_README, ONBOARDING):
        meta = _frontmatter(path)
        assert required <= meta.keys()
        assert meta["source_commit"]
        assert meta["manual_edit"] in {"true", "false"}


def test_docs_readme_routes_humans_and_agents_to_onboarding_hub() -> None:
    text = _read(DOCS_README)

    assert "docs/onboarding/README.md" in text
    assert "Developer" in text
    assert "AI agent" in text
    assert "source-of-truth" in text
    assert "docs/specs/" in text


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


def test_active_graphify_contracts_use_force_and_current_extract_forms() -> None:
    project_context = _read(PROJECT_CONTEXT)
    vault_build = _read(VAULT_BUILD)
    vault_export = _read(VAULT_EXPORT)

    assert "graphify update . --force" in project_context
    assert "graphify update .`" not in project_context
    assert "graphify build" not in vault_export
    assert "graphify extract <repo> --no-cluster" in vault_build
    assert "graphify extract --no-cluster" not in vault_build
