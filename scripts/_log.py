"""Tiny structured-logging helper for auto-pilot scripts."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|password|secret|credential|authorization|auth)", re.IGNORECASE)
_SECRET_VALUE_RE = re.compile(r"\b(Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,})\b")

_RUN_ID: str | None = None


def _resolve_run_id() -> str:
    """Source the active run_id once: env override, else state.json, else ''."""
    global _RUN_ID
    if _RUN_ID is not None:
        return _RUN_ID
    env = os.environ.get("AUTO_PILOT_RUN_ID")
    if env:
        _RUN_ID = env
        return _RUN_ID
    try:
        data = json.loads(Path(".planning/auto-pilot/state.json").read_text())
        val = data.get("run_id", "") if isinstance(data, dict) else ""
        _RUN_ID = val if isinstance(val, str) else ""
    except (OSError, json.JSONDecodeError, ValueError):
        _RUN_ID = ""
    return _RUN_ID


def _redact_value(key: str, value: Any) -> str:
    text = str(value)
    if _SECRET_KEY_RE.search(key) or _SECRET_VALUE_RE.search(text):
        return "<redacted>"
    return text


def event(name: str, **kv: Any) -> None:
    """Emit `ts=<iso> run_id=<id> event=<name> k1=v1 ...` to stderr."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    parts = [f"ts={ts}", f"run_id={_resolve_run_id()}", f"event={name}"]
    for k, v in kv.items():
        parts.append(f"{k}={_redact_value(k, v)}")
    sys.stderr.write(" ".join(parts) + "\n")
