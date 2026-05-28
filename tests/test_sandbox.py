"""Tests for PR3 reviewer sandbox: agents, hook, wrapper."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _parse_frontmatter(md_path: Path) -> dict:
    """Parse the leading YAML frontmatter block delimited by ---."""
    text = md_path.read_text()
    assert text.startswith("---\n"), f"{md_path} missing frontmatter"
    end = text.index("\n---\n", 4)
    block = text[4:end]
    fm: dict = {}
    for line in block.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm


def test_claude_reviewer_agent_frontmatter():
    md = ROOT / "agents" / "auto-pilot-claude-reviewer.md"
    fm = _parse_frontmatter(md)
    assert fm["name"] == "auto-pilot-claude-reviewer"
    assert fm["model"] == "opus"
    tools = {t.strip() for t in fm["tools"].split(",")}
    assert tools == {"Read", "Grep", "Glob", "Bash", "Write"}


def test_codex_reviewer_agent_frontmatter():
    md = ROOT / "agents" / "auto-pilot-codex-reviewer.md"
    fm = _parse_frontmatter(md)
    assert fm["name"] == "auto-pilot-codex-reviewer"
    assert fm["model"] == "opus"
    tools = {t.strip() for t in fm["tools"].split(",")}
    assert tools == {"Read", "Grep", "Glob", "Bash", "Write"}


def test_codex_reviewer_template_mandates_sandbox_read_only():
    md = ROOT / "agents" / "auto-pilot-codex-reviewer.md"
    body = md.read_text()
    assert "--sandbox read-only" in body, \
        "codex reviewer template must include --sandbox read-only literal"
