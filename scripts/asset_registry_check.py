#!/usr/bin/env python3
"""
⓪-10 asset_registry_check.py — creation-gate registry overlap checker.

Registry SoT: live scan of:
  agents/*.md
  skills/*/SKILL.md
  hooks/*.{sh,py}
  commands/*.md

No new registry file — live scan only.

Usage:
  python3 scripts/asset_registry_check.py --fail-on-overlap [--name X --description "..."]
  python3 scripts/asset_registry_check.py --fail-on-overlap --emit-artifact <path>

Overlap heuristic:
  - Shared name tokens (word-tokenized, lower-case, stop words excluded)
  - OR >60% description token overlap (Jaccard on token sets)

Exit: 1 on overlap (when --fail-on-overlap), 0 on clean.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple, TextIO

from _log import event

REPO_ROOT = Path(__file__).resolve().parent.parent
STOP_WORDS = frozenset(
    {"a", "an", "the", "and", "or", "of", "in", "to", "for", "on", "with",
     "at", "by", "from", "as", "is", "it", "be", "this", "that", "are",
     "use", "when", "how", "what", "which", "you", "your", "my", "our",
     "can", "will", "do", "not", "all", "any", "has", "have", "was", "were"}
)


class Asset(NamedTuple):
    """Represent Asset data for this module."""
    name: str
    description: str
    source: str
    asset_type: str


def _write_line(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")


def _warn(message: str) -> None:
    _write_line(sys.stderr, message)


def _tokenize(text: str) -> frozenset[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(t for t in tokens if t not in STOP_WORDS and len(t) > 1)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract name/description from YAML-style frontmatter."""
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
        assets.append(Asset(fm.get("name", f.stem), fm.get("description", ""), str(f.relative_to(REPO_ROOT)), "agent"))
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
        assets.append(Asset(fm.get("name", skill_dir.name), fm.get("description", ""),
                            str(skill_file.relative_to(REPO_ROOT)), "skill"))
    return assets


def _scan_hooks() -> list[Asset]:
    assets: list[Asset] = []
    hooks_dir = REPO_ROOT / "hooks"
    if not hooks_dir.exists():
        return assets
    for f in hooks_dir.iterdir():
        if f.suffix not in {".sh", ".py"} or f.name == "hooks.json" or f.name.startswith("test_"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        desc_match = re.search(r"^#\s*(.+)", text, re.MULTILINE)
        desc = desc_match.group(1).strip() if desc_match else ""
        assets.append(Asset(f.stem, desc, str(f.relative_to(REPO_ROOT)), "hook"))
    return assets


def _scan_commands() -> list[Asset]:
    assets: list[Asset] = []
    cmd_dir = REPO_ROOT / "commands"
    if not cmd_dir.exists():
        return assets
    for f in cmd_dir.glob("*.md"):
        fm = _parse_frontmatter(f.read_text(encoding="utf-8", errors="replace"))
        assets.append(Asset(fm.get("name", f.stem), fm.get("description", ""),
                            str(f.relative_to(REPO_ROOT)), "command"))
    return assets


def _scan_registry() -> list[Asset]:
    registry: list[Asset] = []
    registry.extend(_scan_agents())
    registry.extend(_scan_skills())
    registry.extend(_scan_hooks())
    registry.extend(_scan_commands())
    return registry


def _get_head_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).strip()
    except subprocess.TimeoutExpired:
        event("asset_registry.head_sha_timeout", error_type="TimeoutExpired")
        _warn("asset_registry_check: git rev-parse timed out, returning empty sha")
        return ""
    except (OSError, subprocess.CalledProcessError) as exc:
        event("asset_registry.head_sha_failed", error_type=type(exc).__name__)
        return ""


def _check_overlap(candidate_name: str, candidate_desc: str, registry: list[Asset]) -> list[dict[str, str]]:
    """Return list of overlapping assets for a candidate."""
    c_name_tokens = _tokenize(candidate_name)
    c_desc_tokens = _tokenize(candidate_desc)
    overlaps: list[dict[str, str]] = []
    for asset in registry:
        shared_name = c_name_tokens & _tokenize(asset.name)
        if shared_name:
            overlaps.append({"source": asset.source, "name": asset.name,
                             "reason": f"shared name tokens: {sorted(shared_name)}"})
            continue
        a_desc_tokens = _tokenize(asset.description)
        if c_desc_tokens and a_desc_tokens:
            union = c_desc_tokens | a_desc_tokens
            intersection = c_desc_tokens & a_desc_tokens
            jaccard = len(intersection) / len(union) if union else 0.0
            if jaccard > 0.60:
                overlaps.append({"source": asset.source, "name": asset.name,
                                 "reason": f"description Jaccard {jaccard:.2f} > 0.60"})
    return overlaps


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Asset registry overlap checker (creation gate)")
    parser.add_argument("--fail-on-overlap", action="store_true", help="Exit 1 if overlap detected")
    parser.add_argument("--name", default="", help="Candidate asset name to check against registry")
    parser.add_argument("--description", default="", help="Candidate asset description to check against registry")
    parser.add_argument("--emit-artifact", metavar="PATH", default="", help="Write overlap-check artifact JSON")
    return parser


def _evaluate_candidate(args: argparse.Namespace, registry: list[Asset]) -> tuple[str, list[dict[str, str]]]:
    if not (args.name or args.description):
        event("asset_registry.summary", registry_count=len(registry))
        _warn(f"[asset_registry_check] Registry: {len(registry)} assets scanned")
        return "clean", []
    overlaps = _check_overlap(args.name, args.description, registry)
    if not overlaps:
        event("asset_registry.clean", registry_count=len(registry))
        _warn(f"[asset_registry_check] clean — no overlap for '{args.name}'")
        return "clean", []
    event("asset_registry.overlap", registry_count=len(registry), overlap_count=len(overlaps))
    _warn(f"[asset_registry_check] OVERLAP detected for '{args.name}':")
    for overlap in overlaps:
        _warn(f"  {overlap['source']} ({overlap['name']}): {overlap['reason']}")
    return "overlap", overlaps


def _write_artifact(path: str, result: str, registry_count: int, overlaps: list[dict[str, str]]) -> None:
    artifact_path = Path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "generated_ts": int(time.time()),
        "head_sha": _get_head_sha(),
        "result": result,
        "registry_count": registry_count,
        "overlaps": overlaps,
    }
    artifact_path.write_text(json.dumps(artifact, indent=2))
    event("asset_registry.artifact_written", path=artifact_path, result=result)
    _warn(f"[asset_registry_check] Artifact written to {artifact_path}")


def main() -> int:
    """Run the asset-registry-check command-line entry point."""
    args = _build_parser().parse_args()
    registry = _scan_registry()
    result, overlaps = _evaluate_candidate(args, registry)
    if args.emit_artifact:
        _write_artifact(args.emit_artifact, result, len(registry), overlaps)
    return 1 if args.fail_on_overlap and result == "overlap" else 0


if __name__ == "__main__":
    sys.exit(main())
