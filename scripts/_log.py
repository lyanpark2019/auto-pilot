"""Tiny structured-logging helper for auto-pilot scripts."""
from __future__ import annotations

import re
import sys
from typing import Any

_SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|password|secret|credential|authorization|auth)", re.IGNORECASE)
_SECRET_VALUE_RE = re.compile(r"\b(Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,})\b")


def _redact_value(key: str, value: Any) -> str:
    text = str(value)
    if _SECRET_KEY_RE.search(key) or _SECRET_VALUE_RE.search(text):
        return "<redacted>"
    return text


def event(name: str, **kv: Any) -> None:
    """Emit `event=<name> k1=v1 k2=v2 ...` to stderr."""
    parts = [f"event={name}"]
    for k, v in kv.items():
        parts.append(f"{k}={_redact_value(k, v)}")
    sys.stderr.write(" ".join(parts) + "\n")
