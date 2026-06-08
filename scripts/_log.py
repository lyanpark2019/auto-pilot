"""Tiny structured-logging helper for auto-pilot scripts."""
from __future__ import annotations

import sys
from typing import Any


def event(name: str, **kv: Any) -> None:
    """Emit `event=<name> k1=v1 k2=v2 ...` to stderr."""
    parts = [f"event={name}"]
    for k, v in kv.items():
        parts.append(f"{k}={v}")
    sys.stderr.write(" ".join(parts) + "\n")
