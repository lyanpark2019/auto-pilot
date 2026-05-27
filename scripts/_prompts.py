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

    Always invokes `str.format_map`. Raises `KeyError` if the prompt
    contains a placeholder the caller didn't supply — this is the
    intended safety contract: silent template leaks (raw `{key}` reaching
    the LLM) are far worse than a loud crash.

    For prompts that are pure static content (e.g. the `headless`
    preamble, which contains literal shell `${VAR:-default}` expansions),
    use `load(name)` instead. `render()` of such a prompt will KeyError
    because `format_map` cannot distinguish a shell `${...}` literal from
    a Python `{...}` field.
    """
    return load(name).format_map(vars)
