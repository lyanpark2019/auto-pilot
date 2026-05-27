"""Prompt loader for auto-pilot. Reads from <repo>/prompts/<name>.md."""
from __future__ import annotations
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

def load(name: str) -> str:
    """Return raw prompt text for `prompts/<name>.md`."""
    return (PROMPTS_DIR / f"{name}.md").read_text()

def render(name: str, **vars: Any) -> str:
    """Load prompt and resolve `{key}` placeholders with `vars`.

    When no vars are passed, returns the raw text unchanged so prompts
    containing literal `{...}` (e.g. shell `${VAR:-default}` expansions)
    can be loaded via `render()` without triggering `format_map`.
    """
    text = load(name)
    if not vars:
        return text
    return text.format_map(vars)
