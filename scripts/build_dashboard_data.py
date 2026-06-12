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
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCORE_DIR = ROOT / ".planning" / "score"
OUT = ROOT / "dashboard" / "data.js"

SUBSYSTEM_RULES: list[tuple[str, str]] = [
    (r"^doc-management$", "docs-core"),
    (r"^(vault|nbm)", "docs-vault-export"),
    (r"^(swarm|autopilot-swarm)", "swarm"),
    (r"^(harness|setup-harness|setup-claude-md)", "harness"),
    (r"^(adversarial-review-loop|quality|pm-quality|residue-audit|code-perfector)", "quality"),
    (r"^(auto-pilot|eval-run|worker$|pm-orchestrator$|retro$)", "core-loop"),
    (r"(reviewer|review-gatekeeper|tech-critic|specialist-pool)", "review"),
    (r"^(sha-deploy|deploy)", "deploy"),
    (r"^(codex-orchestra)", "conductor"),
    (r"^(goal-)", "goal"),
    (r"^(diagnosing|improve-codebase)", "diagnostics"),
]


def subsystem_of(name: str) -> str:
    """Provide the public subsystem of API."""
    for pattern, sub in SUBSYSTEM_RULES:
        if re.search(pattern, name):
            return sub
    return "other"


def collect_assets() -> list[dict[str, str]]:
    """Provide the public collect assets API."""
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


def load_rounds() -> list[dict[str, Any]]:
    """Load rounds data."""
    rounds: list[dict[str, Any]] = []
    if SCORE_DIR.is_dir():
        for f in sorted(SCORE_DIR.glob("round-*.json")):
            try:
                loaded = json.loads(f.read_text())
            except json.JSONDecodeError:
                continue
            if isinstance(loaded, dict):
                rounds.append(loaded)
    return rounds


def weighted(s: dict[str, Any]) -> float:
    """Provide the public weighted API."""
    def num(key: str) -> float:
        v = s.get(key, 0)
        return float(v) if isinstance(v, (int, float)) else 0.0

    return round(num("core_fit") * 0.4 + num("uniqueness") * 0.25
                 + num("evidence") * 0.2 + num("cost") * 0.15, 1)


ARCH_HTML_OUT = ROOT / "dashboard" / "architecture.html"

# Pillar definitions (source: docs/architecture.md §System Anatomy)
PILLARS = [
    ("P① 자율 코딩 루프", "core-loop",
     "PM-worker-이중리뷰. Contract-based dispatch, frozen-diff dual adversarial review, fixer convergence.",
     "#3fb950"),
    ("P② 문서 신선도", "docs",
     "doc-management flagship. REBUILD/AUDIT/MAINTAIN 3 modes; stale-doc assets absorbed or REMOVE.",
     "#d29922"),
    ("P③ 지식 영속", "knowledge",
     "vault · retro · memory. Obsidian vault primary context, retro append-only, session handoff.",
     "#bc8cff"),
    ("P④ 안전·집행", "safety",
     "hooks · contracts · gates. Enforcement-not-instruction; mechanical compensation for operator weaknesses.",
     "#f85149"),
]

# Subsystem → pillar mapping (best-fit per subsystem)
SUBSYSTEM_PILLAR: dict[str, str] = {
    "core-loop": "core-loop",
    "review": "core-loop",
    "conductor": "core-loop",
    "quality": "core-loop",
    "docs-core": "docs",
    "docs-vault-export": "docs",
    "diagnostics": "docs",
    "knowledge": "knowledge",
    "swarm": "core-loop",
    "harness": "safety",
    "deploy": "safety",
    "goal": "core-loop",
    "other": "safety",
}

BINDING_CONTRACTS = [
    ("worker contract", "schemas/contract.schema.json",
     "v2: target_repo · target_layer · hard_constraints · snapshot_shas · additionalProperties:false fail-closed"),
    ("reviewer contract", "agents/auto-pilot-codex-reviewer.md + auto-pilot-claude-reviewer.md",
     "read-only sandbox + frozen diff + structured APPROVE/REJECT/ABSTAIN + round-budget gate"),
    ("PM contract", "agents/pm-orchestrator.md",
     "reporting format · prohibited actions · code-edit 0"),
    ("preflight contract", "schemas/preflight.schema.json",
     "phase-key · TTL 900s · head_sha — round-2 addition"),
]


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _render_pillar_cards(sub_counts: dict[str, int]) -> str:
    """Build HTML for the 4-pillar cards block."""
    html = ""
    for label, pillar_id, desc, color in PILLARS:
        subs = [s for s, p in SUBSYSTEM_PILLAR.items() if p == pillar_id]
        count = sum(sub_counts.get(s, 0) for s in subs)
        html += (
            f'<div class="card" style="border-top:3px solid {_esc(color)}">'
            f'<div class="pill" style="background:rgba(0,0,0,.2);border:1px solid {_esc(color)};color:{_esc(color)}">'
            f"{_esc(label)}</div>"
            f"<p class=\"desc\">{_esc(desc)}</p>"
            f'<div class="count-badge">{count} assets</div>'
            f"</div>\n"
        )
    return html


def _render_asset_rows(assets: list[dict[str, str]]) -> str:
    """Build HTML table rows for the asset→pillar mapping table."""
    html = ""
    for a in sorted(assets, key=lambda x: (x["type"], x["name"])):
        sub = subsystem_of(a["name"])
        pillar_id = SUBSYSTEM_PILLAR.get(sub, "safety")
        pillar_color = next((c for _, pid, _, c in PILLARS if pid == pillar_id), "#8b949e")
        html += (
            f'<tr><td><code>{_esc(a["name"])}</code></td>'
            f'<td class="dim">{_esc(a["type"])}</td>'
            f'<td class="dim">{_esc(sub)}</td>'
            f'<td><span style="color:{_esc(pillar_color)};font-size:10.5px">{_esc(pillar_id)}</span></td></tr>\n'
        )
    return html


def _render_contract_rows() -> str:
    """Build HTML table rows for the binding contracts table."""
    html = ""
    for name, file_, desc in BINDING_CONTRACTS:
        html += (
            f"<tr><td><b>{_esc(name)}</b></td>"
            f"<td><code>{_esc(file_)}</code></td>"
            f"<td class=\"dim\">{_esc(desc)}</td></tr>\n"
        )
    return html


def _render_count_badges(counts: dict[str, int]) -> str:
    """Build HTML count-badge divs for the asset counts section."""
    return "".join(
        f'<div class="cb"><span class="n">{v}</span><span class="t">{k}</span></div>'
        for k, v in sorted(counts.items())
    )


_ARCH_CSS = (
    "*{box-sizing:border-box;margin:0;padding:0}"
    "body{background:#0d1117;color:#e6edf3;font-family:-apple-system,Pretendard,sans-serif;padding:28px;line-height:1.5}"
    "h1{font-size:20px;margin-bottom:4px}"
    "h2{font-size:14px;margin:24px 0 8px;color:#58a6ff;border-bottom:1px solid #30363d;padding-bottom:4px}"
    ".sub{color:#8b949e;font-size:11.5px;margin-bottom:18px}"
    "code{background:#161b22;border:1px solid #30363d;border-radius:4px;padding:0 5px;font-size:10.5px;color:#56d4dd}"
    ".pillars{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}"
    ".card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px}"
    ".pill{display:inline-block;font-size:10px;padding:1px 8px;border-radius:10px;margin-bottom:6px;font-weight:600}"
    ".desc{font-size:11px;color:#8b949e;margin-top:4px}"
    ".count-badge{margin-top:8px;font-size:11px;color:#8b949e}"
    "table{width:100%;border-collapse:collapse;font-size:11.5px;margin-top:6px}"
    "th,td{border:1px solid #30363d;padding:5px 8px;text-align:left;vertical-align:top}"
    "th{background:#1c2230;font-size:10.5px}"
    ".dim{color:#8b949e}"
    ".counts{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}"
    ".cb{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:6px 12px;text-align:center}"
    ".cb .n{display:block;font-size:18px;font-weight:700}"
    ".cb .t{display:block;font-size:9.5px;color:#8b949e}"
    ".process{font-family:monospace;background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;font-size:11.5px;white-space:pre;line-height:1.7;color:#e6edf3;margin-top:6px}"
    "footer{margin-top:24px;font-size:10px;color:#8b949e;border-top:1px solid #30363d;padding-top:8px}"
    "@media(max-width:900px){.pillars{grid-template-columns:repeat(2,1fr)}}"
)


def _render_arch_body(
    head: str, branch: str, generated: str, total: int,
    count_badges: str, pillar_cards: str, contract_rows: str, asset_rows_html: str,
) -> str:
    """Render the HTML body section for the architecture page."""
    process_text = (
        "PM (code-edit 0)\n"
        "  → phase plan + tech-critic gate\n"
        "  → contract 발행  [⛓ contract.schema.json · snapshot_shas SHA-pin · idempotency_token]\n"
        "  → worker dispatch  (Sonnet 1M · worktree isolation)\n"
        "  → diff + verify-log  [⛓ SHA-256 mandatory — missing = bounce]\n"
        "  → dual review  [⛓ Codex read-only + cold Claude · PM-frozen diff]\n"
        "  → fixer commit + re-review\n"
        "  → merge (human checkpoint)\n"
        "  → retro → memory  [⛓ vault gotchas + .claude/insights.md]"
    )
    return (
        f'<h1>auto-pilot — Architecture</h1>\n'
        f'<div class="sub">branch <code>{_esc(branch)}</code> · commit <code>{_esc(head)}</code>'
        f' · generated {_esc(generated)} · SoT: <code>docs/architecture.md</code>'
        f' + <code>scripts/build_dashboard_data.collect_assets()</code></div>\n\n'
        f'<h2>Asset counts</h2>\n'
        f'<div class="counts">{count_badges}<div class="cb"><span class="n">{total}</span>'
        f'<span class="t">total</span></div></div>\n\n'
        f'<h2>4-Pillar purpose (모든 자산은 ≥1 pillar 에 역할 정의 의무)</h2>\n'
        f'<div class="pillars">{pillar_cards}</div>\n\n'
        f'<h2>Coding-loop process (SoT: agents/pm-orchestrator.md)</h2>\n'
        f'<div class="process">{process_text}</div>\n\n'
        f'<h2>Binding contracts</h2>\n'
        f'<table>\n<tr><th>Contract</th><th>File</th><th>Constraint</th></tr>\n{contract_rows}</table>\n\n'
        f'<h2>Asset → pillar mapping (live, from collect_assets())</h2>\n'
        f'<table>\n<tr><th>Asset</th><th>Type</th><th>Subsystem</th><th>Pillar</th></tr>\n{asset_rows_html}</table>\n\n'
        f'<footer>Generated by <code>scripts/build_dashboard_data.py</code>'
        f' — HEAD {_esc(head)}. Stale when code changes without re-run.</footer>\n'
    )


def build_architecture_html(
    assets: list[dict[str, str]],
    counts: dict[str, int],
    head: str,
    branch: str,
    generated: str,
) -> str:
    """Build architecture html artifacts."""
    sub_counts: dict[str, int] = {}
    for a in assets:
        sub = subsystem_of(a["name"])
        sub_counts[sub] = sub_counts.get(sub, 0) + 1
    total = sum(counts.values())
    body = _render_arch_body(
        head, branch, generated, total,
        _render_count_badges(counts),
        _render_pillar_cards(sub_counts),
        _render_contract_rows(),
        _render_asset_rows(assets),
    )
    return (
        '<!DOCTYPE html>\n<html lang="ko">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
        '<title>auto-pilot — Architecture</title>\n'
        f'<style>{_ARCH_CSS}</style>\n'
        f'</head>\n<body>\n{body}</body>\n</html>\n'
    )


def main() -> None:
    """Run the build-dashboard-data command-line entry point."""
    import datetime
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True, timeout=30).stdout.strip()
    branch = subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"],
                             capture_output=True, text=True, timeout=30).stdout.strip()
    assets = collect_assets()
    rounds = load_rounds()
    for rnd in rounds:
        for s in rnd.get("assets", {}).values():
            s["total"] = weighted(s)
    asset_rows: list[dict[str, str]] = [
        {**a, "subsystem": subsystem_of(a["name"])} for a in assets
    ]
    counts: dict[str, int] = {}
    for a in asset_rows:
        counts[a["type"]] = counts.get(a["type"], 0) + 1
    data: dict[str, Any] = {
        "branch": branch, "commit": head,
        "counts": counts,
        "assets": asset_rows,
        "rounds": rounds,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.DASHBOARD_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    sys.stdout.write(f"wrote {OUT} — {len(assets)} assets, {len(rounds)} round(s), HEAD {head}\n")

    # Emit architecture.html
    generated = datetime.date.today().isoformat()
    html = build_architecture_html(assets, counts, head, branch, generated)
    ARCH_HTML_OUT.write_text(html)
    size = ARCH_HTML_OUT.stat().st_size
    sys.stdout.write(f"wrote {ARCH_HTML_OUT} — {size:,} bytes\n")


if __name__ == "__main__":
    main()
