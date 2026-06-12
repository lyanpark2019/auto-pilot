"""Dogfood smoke no-op helper (auto-pilot acceptance harness)."""
from __future__ import annotations


def dogfood_identity(x: int) -> int:
    """Return x unchanged."""
    return x
