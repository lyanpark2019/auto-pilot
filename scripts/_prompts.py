"""Prompt loader for auto-pilot. Reads from <repo>/prompts/<name>.md."""
from __future__ import annotations

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
MAX_LLM_PROMPT_CHARS = 120_000
_SECRET_FIELD_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<key_quote>[\"']?)"
    r"(?P<key>api[_-]?key|token|password|secret|credential|auth)"
    r"(?P=key_quote)(?P<sep>\s*[:=]\s*)"
    r"(?P<value_quote>[\"']?)(?P<value>[^\"'\s,}]+)(?P=value_quote)",
    re.IGNORECASE,
)
_AUTHORIZATION_FIELD_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<key_quote>[\"']?)authorization(?P=key_quote)"
    r"(?P<sep>\s*[:=]\s*)(?P<value_quote>[\"']?)"
    r"(?P<scheme>Bearer\s+)?(?P<value>[^\"'\s,}]+)(?P=value_quote)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class PromptBudgetError(ValueError):
    """Raised when rendered prompt output exceeds the configured character cap."""


def load(name: str) -> str:
    """Return raw prompt text for `prompts/<name>.md`."""
    return (PROMPTS_DIR / f"{name}.md").read_text()


def render(name: str, **vars: object) -> str:
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


def _redact_secret_field(match: re.Match[str]) -> str:
    quote = match.group("key_quote")
    value_quote = match.group("value_quote")
    return f"{quote}{match.group('key')}{quote}{match.group('sep')}{value_quote}<redacted>{value_quote}"


def _redact_authorization_field(match: re.Match[str]) -> str:
    quote = match.group("key_quote")
    value_quote = match.group("value_quote")
    scheme = match.group("scheme") or ""
    return f"{quote}authorization{quote}{match.group('sep')}{value_quote}{scheme}<redacted>{value_quote}"


def sanitize_for_llm(text: str, *, max_chars: int = MAX_LLM_PROMPT_CHARS) -> str:
    """Return prompt text safe for an LLM call, or raise on prompt budget overflow."""
    cleaned = _ANSI_CSI_RE.sub("", text)
    cleaned = _CONTROL_CHAR_RE.sub("", cleaned)
    cleaned = _AUTHORIZATION_FIELD_RE.sub(_redact_authorization_field, cleaned)
    cleaned = _SECRET_FIELD_RE.sub(_redact_secret_field, cleaned)
    cleaned = _BEARER_RE.sub("Bearer <redacted>", cleaned)
    cleaned = _OPENAI_KEY_RE.sub("sk-<redacted>", cleaned)
    if max_chars < 1:
        raise PromptBudgetError(f"max_chars must be >=1, got {max_chars}")
    if len(cleaned) > max_chars:
        raise PromptBudgetError(
            f"rendered prompt length {len(cleaned)} exceeds cap {max_chars}"
        )
    return cleaned


def render_for_llm(
    name: str, *, max_chars: int = MAX_LLM_PROMPT_CHARS, **vars: object
) -> str:
    """Render a prompt and apply LLM-call redaction, control scrub, and size cap."""
    return sanitize_for_llm(render(name, **vars), max_chars=max_chars)
