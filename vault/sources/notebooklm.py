#!/usr/bin/env python3
"""NotebookLM source adapter.

Discovers notebooks via `notebooklm list --json`, classifies them by title
heuristic, bootstraps a per-category Obsidian tree, downloads fulltext per source.

Migrated from notebooklm-vault-builder/scripts/{classify,bootstrap_wiki,dl_fulltext,restructure}.py.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from sources._adapter import SourceItem, TicketPlanEntry, register

SUBS = ("concepts", "entities", "decisions", "flows", "components", "research", "sources", "archive")


def _is_match_analysis(title: str, lowered: str) -> bool:
    return (
        bool(re.match(r"team_(mlb|laliga|kbo|npb|nba|kbl|kleague|epl|j[12])_", lowered))
        or bool(re.match(r"league_brief_", lowered))
        or (bool(re.match(r"team\s+", lowered)) and "2026-05" in lowered)
        or any(k in title for k in ["사이넷", "경쟁사", "승부예측"])
        or "라이브스코어" in lowered
    )


def _project_category(lowered: str) -> str | None:
    prefixes = {
        "pickl": "pickl-projects",
        "fyqro": "fyqro-projects",
        "agitrade": "agitrade-projects",
    }
    for prefix, category in prefixes.items():
        if lowered.startswith(prefix) or f"{prefix}-" in lowered:
            return category
    if lowered.startswith("clai") or "clai-" in lowered or "clai " in lowered:
        return "clai-projects"
    if any(k in lowered for k in [
        "sportic365", "스포틱365", "proto", "hermes", "syndicator", "session architecture",
        "reload loop", "team id unification", "auth envelope", "cag", "sportic-server", "ga4-collector",
    ]):
        return "sportic-projects"
    return None


def _is_archive(title: str, lowered: str) -> bool:
    return (
        lowered.startswith("temp-")
        or lowered == "temp-check"
        or "gemma" in lowered
        or "옥션" in title
        or "m5 gpu" in lowered
        or "html to markdown" in lowered
        or any(k in lowered for k in ["paperclip", "mythos", "death of", "blueprint", "claude peers",
                                      "cloudfront", "supabase vector"])
        or lowered in ("code", "design")
        or "tutorial" in lowered
        or "학습" in title
        or "eval-test" in lowered
        or "claude code documentation" in lowered
        or "5가지 에이전트" in title
        or lowered.startswith("job")
        or lowered == "business model"
    )


def _is_ai_library(lowered: str) -> bool:
    return any(k in lowered for k in [
        "symphony", "harness", "archon", "karpathy", "second brain", "voice agent",
        "cli anything", "마케팅 기술", "claude code", "obsidian", "prompt", "ai 자동화",
        "프롬프트", "하네스", "클로드 코드", "코덱스",
    ])


def _is_llm_research(lowered: str) -> bool:
    return any(k in lowered for k in [
        "vs sonnet", "vs opus", "vs haiku", "vs gpt", "model selection", "output control",
        "chat model", "ai engineering", "ibm ai", "ai·llm", "비개발자", "claude opus",
        "claude sonnet", "claude haiku", "llm", "openai", "schema",
    ])


def _classify_title(title: str) -> str:
    """Heuristic mapping title → category."""
    lowered = title.lower()
    if _is_match_analysis(title, lowered):
        return "match-analysis"
    if any(k in title for k in ["농식품", "비관세"]) or any(k in lowered for k in ["fta", "sps", "cbam", "fda"]):
        return "agri-trade"
    if "로또" in title or "연금복권" in title:
        return "lotto"
    category = _project_category(lowered)
    if category:
        return category
    if _is_archive(title, lowered):
        return "archive"
    if _is_ai_library(lowered):
        return "ai-libraries"
    if _is_llm_research(lowered):
        return "llm-research"
    return "uncategorized"


def _slugify(s: str) -> str:
    s = re.sub(r"[^\w\s가-힣\-]", "", s).strip()
    return re.sub(r"\s+", "-", s)[:80]


def _clean_slug(title: str) -> str:
    s = re.sub(r"\b20\d{2}-\d{2}-\d{2}\b", "", title)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"[\s_/\\]+", "-", s)
    s = re.sub(r"[^\w가-힣\-]", "", s)
    return re.sub(r"-+", "-", s).strip("-").lower()[:60]


def _parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("\"'")
    return fm


def _run(cmd: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -2, "", "notebooklm CLI not found"


@register
class NotebookLMAdapter:
    name = "notebooklm"
    default_rubric = "notebooklm.yaml"

    def discover(self, input_path: Path, **opts: Any) -> list[SourceItem]:
        """Run `notebooklm list --json` and return notebooks as SourceItems."""
        rc, out, err = _run(["notebooklm", "list", "--json"])
        if rc != 0:
            raise RuntimeError(f"notebooklm list failed: {err}")
        data = json.loads(out)
        items = []
        for nb in data.get("notebooks", []):
            items.append(SourceItem(
                id=nb["id"],
                label=nb["title"],
                kind="notebook",
                category=_classify_title(nb["title"]),
                payload=nb,
            ))
        return items

    def classify(self, items: list[SourceItem], **opts: Any) -> dict[str, list[SourceItem]]:
        buckets: dict[str, list[SourceItem]] = {}
        for it in items:
            buckets.setdefault(it.category, []).append(it)
        return buckets

    def bootstrap(self, vault: Path, buckets: dict[str, list[SourceItem]], **opts: Any) -> None:
        vault = vault.expanduser().resolve()
        cats = [c for c in buckets if c not in ("archive", "uncategorized")]
        (vault / "meta").mkdir(parents=True, exist_ok=True)
        (vault / "meta" / "categories.json").write_text(json.dumps(cats, ensure_ascii=False))
        (vault / "meta" / "buckets.json").write_text(
            json.dumps({c: [it.payload for it in v] for c, v in buckets.items()},
                       ensure_ascii=False, indent=2)
        )

        from datetime import date
        today = date.today().isoformat()

        for c in cats:
            d = vault / c
            d.mkdir(exist_ok=True)
            (d / "raw").mkdir(exist_ok=True)
            for s in SUBS:
                (d / s).mkdir(exist_ok=True)
                idx = d / s / "_index.md"
                if not idx.exists():
                    idx.write_text(f"---\ntype: index\nfolder: {s}\ncategory: {c}\ncreated: {today}\n---\n\n# {c} / {s}\n")
            for fname, body in [
                ("index.md", f"---\ntype: index\ncategory: {c}\ncreated: {today}\n---\n\n# {c}\n\n- [[overview]] [[hot]] [[log]]\n- sources/ concepts/ entities/ decisions/\n"),
                ("overview.md", f"---\ntype: overview\ncategory: {c}\n---\n\n# {c} — Overview\n"),
                ("hot.md", f"---\ntype: meta\ntitle: \"Hot Cache — {c}\"\ntags: [meta, cache]\nstatus: developing\n---\n\n# Hot Cache — {c}\n"),
                ("log.md", f"---\ntype: log\ncategory: {c}\n---\n\n# Ingest Log — {c}\n\n| date | action | target | note |\n|---|---|---|---|\n"),
            ]:
                target = d / fname
                if not target.exists():
                    target.write_text(body)

        root_idx = vault / "index.md"
        root_idx.write_text(f"---\ntype: index\ncreated: {today}\n---\n\n# {vault.name}\n\n"
                            + "\n".join(f"- [[{c}/index|{c}]]" for c in cats))

    def _source_list(self, nid: str) -> tuple[list[dict[str, Any]] | None, str]:
        rc, src_json, err = _run(["notebooklm", "source", "list", "--notebook", nid, "--json"])
        if rc != 0:
            return None, err[:120]
        try:
            data = json.loads(src_json)
        except json.JSONDecodeError:
            return None, "parse"
        sources = data.get("sources", []) if isinstance(data, dict) else []
        return [s for s in sources if isinstance(s, dict)], ""

    def _notebook_archive_parts(self, cat: str, nb: dict[str, Any], sources: list[dict[str, Any]]) -> list[str]:
        nid, title = nb["id"], nb["title"]
        parts = ["---", "type: notebook-archive", f"notebook_id: {nid}",
                 f"title: {json.dumps(title, ensure_ascii=False)}", f"created_at: {nb.get('created_at', '')}",
                 f"category: {cat}", f"source_count: {len(sources)}", "---", "", f"# {title}", "", "## Sources", ""]
        for source in sources:
            parts.append(f"- {source.get('title', '?')} (`{source['id'][:8]}`)")
        parts += ["", "## Fulltext", ""]
        return parts

    def _append_fulltext(self, parts: list[str], nid: str, sources: list[dict[str, Any]]) -> None:
        for source in sources:
            rc, st, _ = _run(["notebooklm", "source", "fulltext", source["id"], "-n", nid, "--json"], timeout=60)
            try:
                content = json.loads(st).get("content", "") if rc == 0 else "(fetch failed)"
            except json.JSONDecodeError:
                content = "(parse error)"
            parts += [f"### {source.get('title', '?')}", "", content[:200_000], ""]

    def _materialize_one(self, vault: Path, cat: str, nb: dict[str, Any]) -> str:
        nid, title = nb["id"], nb["title"]
        slug = _slugify(title) or nid[:8]
        out = vault / cat / "raw" / f"{slug}.md"
        if out.exists() and out.stat().st_size > 200:
            return f"SKIP {cat}/{slug}"
        sources, err = self._source_list(nid)
        if sources is None:
            return f"FAIL {'parse' if err == 'parse' else 'src-list'} {nid[:8]}{': ' + err if err != 'parse' else ''}"
        parts = self._notebook_archive_parts(cat, nb, sources)
        self._append_fulltext(parts, nid, sources)
        out.write_text("\n".join(parts))
        return f"OK {cat}/{slug} ({len(sources)} sources)"

    def materialize(self, vault: Path, buckets: dict[str, list[SourceItem]], **opts: Any) -> None:
        vault = vault.expanduser().resolve()
        preserve = {c: v for c, v in buckets.items() if c not in ("archive", "uncategorized")}
        jobs = [(c, it.payload) for c, items in preserve.items() for it in items]
        parallel = opts.get("parallel", 6)
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            futs = {ex.submit(self._materialize_one, vault, c, nb): (c, nb) for c, nb in jobs}
            for i, f in enumerate(as_completed(futs), 1):
                sys.stdout.write(f"[{i}/{len(jobs)}] {f.result()}\n")
                sys.stdout.flush()
        self._restructure(vault)

    def _restructure(self, vault: Path) -> None:
        """Rename raw/*.md to YYYY-MM-DD_slug_id8.md + generate sources/_index.md."""
        cats = json.loads((vault / "meta" / "categories.json").read_text())
        for c in cats:
            raw = vault / c / "raw"
            src = vault / c / "sources"
            src.mkdir(exist_ok=True)
            entries = []
            for f in sorted(raw.glob("*.md")):
                text = f.read_text()
                fm = _parse_frontmatter(text)
                nid = fm.get("notebook_id", "unknown")
                title = fm.get("title", "")
                created = fm.get("created_at", "2026-01-01")[:10]
                slug = _clean_slug(title) if title else f.stem
                new = f"{created}_{slug}_{nid[:8]}.md"
                if f.name != new:
                    f.rename(raw / new)
                sc = fm.get("source_count", "?")
                (src / new).write_text(
                    f"---\ntype: source\nnotebook_id: {nid}\ntitle: \"{title}\"\n"
                    f"created_at: {created}\ncategory: {c}\nsource_count: {sc}\n"
                    f"raw: \"../raw/{new}\"\n---\n\n# {title}\n\n"
                    f"- ID: `{nid}` Created: {created}\n- Sources: {sc}\n"
                    f"- Raw: [[../raw/{new[:-3]}]]\n\n## Cross-links\n\n"
                    f"- [[../index]] [[../hot]] [[../../meta/cross-vault-links|cross-vault]]\n"
                )
                entries.append((created, slug, nid[:8], title, sc))
            lines = ["---", "type: index", "folder: sources",
                     f"category: {c}", f"count: {len(entries)}", "---", "", f"# {c} / sources", "",
                     "| date | title | id | sources | page |",
                     "|---|---|---|---|---|"]
            for cr, sl, i8, ti, sc in sorted(entries):
                lines.append(f"| {cr} | {ti} | `{i8}` | {sc} | [[{cr}_{sl}_{i8}]] |")
            (src / "_index.md").write_text("\n".join(lines))

    def plan_tickets(self, vault: Path, round_num: int, score_state: dict, **opts: Any) -> list[TicketPlanEntry]:
        """Map low-scoring dims to worker tickets. PM uses this as starting plan."""
        plan = []
        scores = score_state.get("scores", {})
        # Mapping mirrors agents/vault-pm-orchestrator.md Worker → Dimension table
        WORKER_FOR_DIM = {
            "graph_density": "vault-graph-enricher",
            "confidence_balance": "vault-edge-curator",
            "concept_entity_depth": "vault-knowledge-author",
            "adr_pages": "vault-knowledge-author",
            "cross_vault": "vault-graph-enricher",
            "hot_cache": "vault-graph-enricher",
            "wiki_articles": "vault-structure-curator",
            "bases": "vault-structure-curator",
            "backlinks": "vault-graph-enricher",
            "conflict_dup": "vault-structure-curator",
            "edge_fact": "vault-edge-curator",
            "concept_accuracy": "vault-knowledge-author",
            "adr_fidelity": "vault-knowledge-author",
        }
        for dim, worker in WORKER_FOR_DIM.items():
            current = scores.get(dim)
            if current is None:
                continue
            # Schedule ticket if current < some threshold per rubric.yaml — simplified here
            plan.append(TicketPlanEntry(
                worker_type=worker,
                contract={
                    "goal": f"Improve {dim} dim (current {current})",
                    "target_dimension": dim,
                    "reward": 10,
                },
            ))
        return plan
