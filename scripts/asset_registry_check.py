#!/usr/bin/env python3
"""
⓪-10 asset_registry_check.py — creation-gate registry overlap checker.

Registry SoT: live scan of:
  agents/*.md
  skills/*/SKILL.md
  hooks/*.{sh,py}
  commands/*.md
  codex/skills/*/  (frontmatter name/description)

No new registry file — live scan only.

Usage:
  python3 scripts/asset_registry_check.py --fail-on-overlap [--name X --description "..."]
  python3 scripts/asset_registry_check.py --fail-on-overlap --emit-artifact <path>

Overlap heuristic (document crudeness):
  - Shared name tokens (word-tokenized, lower-case, stop words excluded)
  - OR >60% description token overlap (Jaccard on token sets)
  This is a simple deterministic heuristic. False positives exist for common words.
  Overlap does NOT block — it flags for human review.

Exit: 1 on overlap (when --fail-on-overlap), 0 on clean.

Artifact format (--emit-artifact):
  {"generated_ts": <unix_epoch_int>, "head_sha": "<sha>", "result": "clean"|"overlap",
   "overlaps": [...]}
  (generated_ts matches preflight schema TTL pattern — tech-critic condition)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
STOP_WORDS = frozenset(
    {"a", "an", "the", "and", "or", "of", "in", "to", "for", "on", "with",
     "at", "by", "from", "as", "is", "it", "be", "this", "that", "are",
     "use", "when", "how", "what", "which", "you", "your", "my", "our",
     "can", "will", "do", "not", "all", "any", "has", "have", "was", "were"}
)


class Asset(NamedTuple):
    name: str
    description: str
    source: str  # relative path
    asset_type: str  # agent|skill|hook|command|codex


def _tokenize(text: str) -> frozenset[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(t for t in tokens if t not in STOP_WORDS and len(t) > 1)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract name/description from YAML-style frontmatter (--- ... ---)."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    result: dict[str, str] = {}
    for line in m.group(1).splitlines():
        kv = re.match(r"^(\w+)\s*:\s*(.+)$", line.strip())
        if kv:
            result[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")
    return result


def _scan_agents() -> list[Asset]:
    assets = []
    for f in (REPO_ROOT / "agents").glob("*.md"):
        fm = _parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        name = fm.get("name", f.stem)
        desc = fm.get("description", "")
        assets.append(Asset(name=name, description=desc, source=str(f.relative_to(REPO_ROOT)), asset_type="agent"))
    return assets


def _scan_skills() -> list[Asset]:
    assets: list[Asset] = []
    skills_dir = REPO_ROOT / "skills"
    if not skills_dir.exists():
        return assets
    for skill_dir in skills_dir.iterdir():
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        fm = _parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="replace"))
        name = fm.get("name", skill_dir.name)
        desc = fm.get("description", "")
        assets.append(Asset(name=name, description=desc, source=str(skill_file.relative_to(REPO_ROOT)), asset_type="skill"))
    return assets


def _scan_hooks() -> list[Asset]:
    assets: list[Asset] = []
    hooks_dir = REPO_ROOT / "hooks"
    if not hooks_dir.exists():
        return assets
    for f in hooks_dir.iterdir():
        # Skip hook test scripts — they are not assets; counting them put this
        # registry at 80 vs build_dashboard_data.collect_assets' canonical 77
        # (review r1 divergence finding).
        if f.suffix in {".sh", ".py"} and f.name != "hooks.json" and not f.name.startswith("test_"):
            # Use filename stem as name, first comment line as description
            text = f.read_text(encoding="utf-8", errors="replace")
            desc_match = re.search(r"^#\s*(.+)", text, re.MULTILINE)
            desc = desc_match.group(1).strip() if desc_match else ""
            assets.append(Asset(name=f.stem, description=desc, source=str(f.relative_to(REPO_ROOT)), asset_type="hook"))
    return assets


def _scan_commands() -> list[Asset]:
    assets: list[Asset] = []
    cmd_dir = REPO_ROOT / "commands"
    if not cmd_dir.exists():
        return assets
    for f in cmd_dir.glob("*.md"):
        fm = _parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        name = fm.get("name", f.stem)
        desc = fm.get("description", "")
        assets.append(Asset(name=name, description=desc, source=str(f.relative_to(REPO_ROOT)), asset_type="command"))
    return assets


def _scan_codex_skills() -> list[Asset]:
    assets: list[Asset] = []
    codex_skills_dir = REPO_ROOT / "codex" / "skills"
    if not codex_skills_dir.exists():
        return assets
    for skill_dir in codex_skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        # Look for SKILL.md or any .md with frontmatter
        for candidate in [skill_dir / "SKILL.md"] + list(skill_dir.glob("*.md")):
            if candidate.exists():
                fm = _parse_frontmatter(candidate.read_text(encoding="utf-8", errors="replace"))
                if fm.get("name") or fm.get("description"):
                    name = fm.get("name", skill_dir.name)
                    desc = fm.get("description", "")
                    assets.append(Asset(name=name, description=desc, source=str(candidate.relative_to(REPO_ROOT)), asset_type="codex"))
                    break
    return assets


def _get_head_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _check_overlap(
    candidate_name: str,
    candidate_desc: str,
    registry: list[Asset],
) -> list[dict[str, str]]:
    """Return list of overlapping assets for a candidate."""
    c_name_tokens = _tokenize(candidate_name)
    c_desc_tokens = _tokenize(candidate_desc)
    overlaps: list[dict[str, str]] = []
    for asset in registry:
        a_name_tokens = _tokenize(asset.name)
        a_desc_tokens = _tokenize(asset.description)

        # Shared name tokens
        shared_name = c_name_tokens & a_name_tokens
        if shared_name:
            overlaps.append({
                "source": asset.source,
                "name": asset.name,
                "reason": f"shared name tokens: {sorted(shared_name)}",
            })
            continue

        # >60% description Jaccard overlap
        if c_desc_tokens and a_desc_tokens:
            union = c_desc_tokens | a_desc_tokens
            intersection = c_desc_tokens & a_desc_tokens
            jaccard = len(intersection) / len(union) if union else 0.0
            if jaccard > 0.60:
                overlaps.append({
                    "source": asset.source,
                    "name": asset.name,
                    "reason": f"description Jaccard {jaccard:.2f} > 0.60",
                })
    return overlaps


def main() -> int:
    parser = argparse.ArgumentParser(description="Asset registry overlap checker (creation gate)")
    parser.add_argument("--fail-on-overlap", action="store_true",
                        help="Exit 1 if overlap detected")
    parser.add_argument("--name", default="",
                        help="Candidate asset name to check against registry")
    parser.add_argument("--description", default="",
                        help="Candidate asset description to check against registry")
    parser.add_argument("--emit-artifact", metavar="PATH", default="",
                        help="Write overlap-check artifact JSON to this path")
    args = parser.parse_args()

    # Scan registry
    registry: list[Asset] = []
    registry.extend(_scan_agents())
    registry.extend(_scan_skills())
    registry.extend(_scan_hooks())
    registry.extend(_scan_commands())
    registry.extend(_scan_codex_skills())

    overlaps: list[dict[str, str]] = []
    result = "clean"

    if args.name or args.description:
        overlaps = _check_overlap(args.name, args.description, registry)
        if overlaps:
            result = "overlap"
            print(f"[asset_registry_check] OVERLAP detected for '{args.name}':", file=sys.stderr)
            for o in overlaps:
                print(f"  {o['source']} ({o['name']}): {o['reason']}", file=sys.stderr)
        else:
            print(f"[asset_registry_check] clean — no overlap for '{args.name}'", file=sys.stderr)
    else:
        # No candidate provided — just emit registry summary
        print(f"[asset_registry_check] Registry: {len(registry)} assets scanned", file=sys.stderr)
        result = "clean"

    if args.emit_artifact:
        artifact_path = Path(args.emit_artifact)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "generated_ts": int(time.time()),
            "head_sha": _get_head_sha(),
            "result": result,
            "registry_count": len(registry),
            "overlaps": overlaps,
        }
        artifact_path.write_text(json.dumps(artifact, indent=2))
        print(f"[asset_registry_check] Artifact written to {artifact_path}", file=sys.stderr)

    if args.fail_on_overlap and result == "overlap":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
