#!/usr/bin/env python3
"""Build dashboard/data.js for the plugin structure + scorecard dashboard.

Walks the plugin tree (skills/agents/commands/hooks/codex) and merges per-round
scorecards from .planning/score/round-*.json. Each loop round of the perfection
workflow writes a new round file; re-running this script refreshes the dashboard.

Round file schema (round-N.json):
{
  "round": 0, "label": "provisional", "generated": "YYYY-MM-DD",
  "assets": { "<type>:<name>": {"core_fit": 0-10, "uniqueness": 0-10,
               "evidence": 0-10, "cost": 0-10, "verdict": "CORE|INTEGRATE|KEEP|REMOVE|PENDING",
               "note": "..."} }
}
Weighted total = core_fit*.4 + uniqueness*.25 + evidence*.2 + cost*.15 (cost = 10 means cheap).
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCORE_DIR = ROOT / ".planning" / "score"
OUT = ROOT / "dashboard" / "data.js"

SUBSYSTEM_RULES: list[tuple[str, str]] = [
    (r"^(doc-management|graphify-doc-rebuild|doc-drift-audit|doc-sync|llm-wiki-architect)$", "docs-core"),
    (r"^(vault|nbm)", "docs-vault-export"),
    (r"^(swarm|autopilot-swarm)", "swarm"),
    (r"^(harness|setup-harness|setup-claude-md)", "harness"),
    (r"^(adversarial-review-loop|quality|pm-quality|residue-audit|code-perfector|codebase-perfection-loop)", "quality"),
    (r"^(auto-pilot|eval-run|worker$|pm-orchestrator$|retro$)", "core-loop"),
    (r"(reviewer|codex-adversarial|tdd-enforcer|security-reviewer|tech-critic|specialist-pool)", "review"),
    (r"^(sha-deploy|deploy)", "deploy"),
    (r"^(codex-orchestra)", "conductor"),
    (r"^(goal-)", "goal"),
    (r"^(diagnosing|improve-codebase)", "diagnostics"),
]


def subsystem_of(name: str) -> str:
    for pattern, sub in SUBSYSTEM_RULES:
        if re.search(pattern, name):
            return sub
    return "other"


def collect_assets() -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    skills = ROOT / "skills"
    if skills.is_dir():
        for d in sorted(skills.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                assets.append({"type": "skill", "name": d.name})
            elif d.is_dir():  # deprecated shells (references kept, SKILL.md removed)
                assets.append({"type": "skill-shell", "name": d.name})
    for sub, typ in (("agents", "agent"), ("commands", "command")):
        base = ROOT / sub
        if base.is_dir():
            for f in sorted(base.glob("*.md")):
                assets.append({"type": typ, "name": f.stem})
    hooks = ROOT / "hooks"
    if hooks.is_dir():
        for f in sorted(hooks.iterdir()):
            if f.suffix in (".py", ".sh") and not f.name.startswith("test_"):
                assets.append({"type": "hook", "name": f.name})
    codex = ROOT / "codex" / "skills"
    if codex.is_dir():
        for d in sorted(codex.iterdir()):
            if d.is_dir():
                assets.append({"type": "codex-skill", "name": d.name})
    return assets


def load_rounds() -> list[dict]:
    rounds: list[dict] = []
    if SCORE_DIR.is_dir():
        for f in sorted(SCORE_DIR.glob("round-*.json")):
            try:
                rounds.append(json.loads(f.read_text()))
            except json.JSONDecodeError:
                continue
    return rounds


def weighted(s: dict) -> float:
    return round(s.get("core_fit", 0) * 0.4 + s.get("uniqueness", 0) * 0.25
                 + s.get("evidence", 0) * 0.2 + s.get("cost", 0) * 0.15, 1)


def main() -> None:
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    branch = subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"],
                            capture_output=True, text=True).stdout.strip()
    assets = collect_assets()
    rounds = load_rounds()
    for rnd in rounds:
        for key, s in rnd.get("assets", {}).items():
            s["total"] = weighted(s)
    data = {
        "branch": branch, "commit": head,
        "counts": {},
        "assets": [{**a, "subsystem": subsystem_of(a["name"])} for a in assets],
        "rounds": rounds,
    }
    for a in data["assets"]:
        data["counts"][a["type"]] = data["counts"].get(a["type"], 0) + 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.DASHBOARD_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    print(f"wrote {OUT} — {len(assets)} assets, {len(rounds)} round(s), HEAD {head}")


if __name__ == "__main__":
    main()
