#!/usr/bin/env python3
"""Code source adapter.

Scans a code repository under `input_path` (CWD by default), classifies modules
into areas (top-level dirs, package boundaries), bootstraps vault structure,
and emits ticket plan for vault-knowledge-author dispatch.

Migrated pattern from ~/.claude/skills/autonomous-docs-loop/.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from sources._adapter import SourceItem, TicketPlanEntry, register
from sources._excludes import is_excluded

CODE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".sql")


def _detect_area(path: Path, root: Path) -> str:
    """First non-trivial path component = area name."""
    parts = path.relative_to(root).parts
    skip = {"src", "app", "lib", "pkg", "internal", ""}
    for p in parts:
        if p not in skip:
            return p
    return parts[0] if parts else "root"


def _write_category_indexes(d: Path, category: str, today: str) -> None:
    for sub in ("concepts", "entities", "decisions", "sources"):
        (d / sub).mkdir(exist_ok=True)
        idx = d / sub / "_index.md"
        if not idx.exists():
            idx.write_text(
                f"---\ntype: index\ncategory: {category}\nsubcategory: {sub}\n"
                f"created: {today}\n---\n\n# {category}/{sub}\n\n"
                f"_Populated by PM-orchestrator workers._\n"
            )


def _category_pages(category: str, today: str) -> list[tuple[str, str]]:
    hot = (
        f"---\ntype: meta\ntitle: \"Hot Cache — {category}\"\nstatus: developing\n---\n\n"
        f"# Hot Cache — {category}\n\n"
        f"## God Nodes\n_Populated by vault-graph-enricher worker._\n\n"
        f"## Cross-bridges\n_Populated by vault-graph-enricher worker._\n\n"
        f"## Source Files\n_Populated by vault-graph-enricher worker._\n\n"
        f"## Quick Questions\n_Populated by vault-graph-enricher worker._\n\n"
        f"## Cross-vault\n_Populated by vault-graph-enricher worker._\n"
    )
    return [
        ("index.md", f"---\ntype: index\ncategory: {category}\ncreated: {today}\n---\n\n# {category}\n\n## Modules\n"),
        ("overview.md", f"---\ntype: overview\ncategory: {category}\n---\n\n# {category} — Overview\n\nPurpose, scope, key abstractions.\n"),
        ("hot.md", hot),
        ("log.md", f"---\ntype: log\ncategory: {category}\n---\n\n# Docs Log — {category}\n\n| date | action | file | note |\n|---|---|---|---|\n"),
    ]


def _write_category_root(vault: Path, category: str, today: str) -> None:
    d = vault / category
    d.mkdir(exist_ok=True)
    (d / "modules").mkdir(exist_ok=True)
    (d / "raw").mkdir(exist_ok=True)
    _write_category_indexes(d, category, today)
    for fname, body in _category_pages(category, today):
        target = d / fname
        if not target.exists():
            target.write_text(body)


def _write_vault_indexes(vault: Path, categories: list[str], today: str) -> None:
    root_idx = vault / "index.md"
    root_idx.write_text(
        f"---\ntype: index\ncreated: {today}\n---\n\n# {vault.name}\n\n"
        + "\n".join(f"- [[{c}/index|{c}]]" for c in categories)
    )
    cv_path = vault / "meta" / "cross-vault-links.md"
    if not cv_path.exists():
        cv_links = "\n".join(f"- [[../{c}/index|{c}]]" for c in categories)
        cv_path.write_text(
            f"---\ntype: meta\ntitle: \"Cross-vault Links\"\ncreated: {today}\n---\n\n"
            f"# Cross-vault Links\n\n"
            f"Internal vault category roots (verified targets for scoring):\n\n"
            f"{cv_links}\n"
        )


@register
class CodeAdapter:
    name = "code"
    default_rubric = "code-docs.yaml"

    def discover(self, input_path: Path, **opts: Any) -> list[SourceItem]:
        root = input_path.expanduser().resolve()
        extras = opts.get("extra_excludes", [])
        items = []
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix not in CODE_EXTS:
                continue
            if is_excluded(p, root, extras):
                continue
            rel = p.relative_to(root)
            items.append(SourceItem(
                id=str(rel),
                label=rel.name,
                kind="module",
                category=_detect_area(p, root),
                payload={"path": str(rel), "ext": p.suffix, "size": p.stat().st_size},
            ))
        return items

    def classify(self, items: list[SourceItem], **opts: Any) -> dict[str, list[SourceItem]]:
        buckets: dict[str, list[SourceItem]] = {}
        for it in items:
            buckets.setdefault(it.category, []).append(it)
        # Drop tiny areas (< 3 files) into "misc"
        misc = []
        keep: dict[str, list[SourceItem]] = {}
        for cat, lst in buckets.items():
            if len(lst) < 3:
                misc.extend(lst)
            else:
                keep[cat] = lst
        if misc:
            keep["misc"] = misc
        return keep

    def bootstrap(self, vault: Path, buckets: dict[str, list[SourceItem]], **opts: Any) -> None:
        vault = vault.expanduser().resolve()
        cats = list(buckets.keys())
        today = date.today().isoformat()
        (vault / "meta").mkdir(parents=True, exist_ok=True)
        (vault / "meta" / "categories.json").write_text(json.dumps(cats, ensure_ascii=False))
        (vault / "meta" / "buckets.json").write_text(
            json.dumps({c: [it.payload for it in v] for c, v in buckets.items()},
                       ensure_ascii=False, indent=2)
        )
        for c in cats:
            _write_category_root(vault, c, today)
        _write_vault_indexes(vault, cats, today)

    def materialize(self, vault: Path, buckets: dict[str, list[SourceItem]], **opts: Any) -> None:
        """No download — code files stay in repo. Write module stubs that workers will fill."""
        vault = vault.expanduser().resolve()
        for cat, items in buckets.items():
            stub_dir = vault / cat / "modules"
            for it in items:
                stub = stub_dir / f"{Path(it.id).stem}.md"
                if stub.exists():
                    continue
                stub.write_text(
                    f"---\ntype: module\ncategory: {cat}\nsource_files: [\"{it.id}\"]\n"
                    f"status: stub\ncreated: {date.today().isoformat()}\n---\n\n"
                    f"# {it.label}\n\n## Purpose\n\n_Pending vault-knowledge-author._\n\n"
                    f"## Public API\n\n## Examples\n\n## Cross-links\n"
                )

    def plan_tickets(
        self,
        vault: Path,
        round_num: int,
        score_state: dict[str, Any],
        **opts: Any,
    ) -> list[TicketPlanEntry]:
        """One ticket per category for vault-knowledge-author to fill stubs."""
        plan = []
        cats = json.loads((vault / "meta" / "categories.json").read_text())
        for cat in cats:
            plan.append(TicketPlanEntry(
                worker_type="vault-knowledge-author",
                contract={
                    "goal": f"Fill module stubs in {cat}/ with hallucination-free docs",
                    "target_category": cat,
                    "rubric": "code-docs.yaml",
                    "reward": 100,
                },
            ))
        return plan
