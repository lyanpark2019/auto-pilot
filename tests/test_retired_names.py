"""Retired-name guard — deterministic gate (review r1 pre-mortem clause).

Round-2 consolidation deleted commands/skills; their names must not appear as
LIVE references in agent/skill/command bodies (a stale `/nbm-to-obsidian`
trigger survived in vault-pm-orchestrator.md). Historical/supersession notes
are fine — lines carrying an explicit retirement marker are allowlisted.

Precedent: PickL-API RETIRED_SYMBOLS denylist (clai-exec reintroduction guard).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Commands/skills deleted in round-2 consolidation (W2 ⓑ)
RETIRED_NAMES = [
    "/nbm-to-obsidian",
    "/vault-audit",
    "/vault-content-verify",
    "/vault-drift",
    "/vault-restructure",
    "/vault-resume",
    "/quality-loop",
    # consolidation-2 (2026-06-07): legacy reviewers + absorbed skills/commands
    "/eval-run",
    "pm-quality-harness-loop",
    "swarm-bench",
    "diagnosing-llm-output-leaks",
    "diagnosing-stale-runtime",
    "code-perfector",
    "codex-adversarial",
    "security-reviewer",
    "tdd-enforcer",
    # consolidation-3 (2026-06-20): dead-feature removal
    "swarm-explorer",
    "swarm-monitor",
    "swarm-verifier",
    "codex-orchestra",
    "improve-codebase-architecture",
    "/swarm",
    "/codex-orchestra",
    "/diagnosing",
]

# A line mentioning a retired name is OK iff it explicitly marks retirement
HISTORICAL_MARKERS = re.compile(
    r"deleted|legacy|superse|replace[sd]|absorb|retired|renamed|alias|"
    r"provenance|merged into|former|adapted|inspired|→",
    re.IGNORECASE,
)

SCAN_GLOBS = ["agents/*.md", "commands/*.md", "skills/*/SKILL.md"]


def _scan() -> list[str]:
    violations: list[str] = []
    for pattern in SCAN_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                for name in RETIRED_NAMES:
                    if name in line and not HISTORICAL_MARKERS.search(line):
                        violations.append(
                            f"{path.relative_to(REPO_ROOT)}:{lineno}: live ref to "
                            f"retired name {name!r}: {line.strip()[:120]}"
                        )
    return violations


def test_no_live_references_to_retired_names() -> None:
    violations = _scan()
    assert not violations, (
        "Retired command/skill names referenced as live (add a retirement "
        "marker like 'deleted'/'absorbed→' if intentional history):\n"
        + "\n".join(violations)
    )
