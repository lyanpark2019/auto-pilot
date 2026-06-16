#!/usr/bin/env python3
"""Reusable stdin-JSON contract validator for hook scripts.

All hooks must read tool input from stdin as JSON (CLAUDE.md rule).
This module enforces that contract with a typed error and two helpers:

- ``read_tool_input`` — strict: raises ``StdinContractError`` on malformed input.
- ``read_tool_input_or_none`` — advisory / fail-open: returns ``None`` on any
  error so advisory hooks can no-op cleanly without blocking workflow.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any, TextIO


class StdinContractError(Exception):
    """Raised when stdin does not conform to the expected hook JSON shape.

    Covers two failure modes:
    - JSON parse failure (not JSON at all)
    - Valid JSON but missing the required ``tool_input`` key (or not a mapping)
    """


def read_tool_input(stream: TextIO = sys.stdin) -> dict[str, Any]:
    """Parse and validate hook stdin, returning ``tool_input`` as a dict.

    Args:
        stream: Readable text stream to parse (defaults to ``sys.stdin``).

    Returns:
        The ``tool_input`` mapping from the hook payload.

    Raises:
        StdinContractError: If stdin is not valid JSON, not an object, or
            lacks a ``tool_input`` key.
    """
    raw = stream.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError) as exc:
        raise StdinContractError(f"stdin is not valid JSON: {exc}") from exc

    if not isinstance(data, Mapping):
        raise StdinContractError(
            f"stdin JSON must be an object (mapping), got {type(data).__name__}"
        )

    if "tool_input" not in data:
        raise StdinContractError(
            "stdin JSON object is missing required key 'tool_input'"
        )

    tool_input = data["tool_input"]
    if not isinstance(tool_input, Mapping):
        raise StdinContractError(
            f"'tool_input' must be a mapping, got {type(tool_input).__name__}"
        )

    return dict(tool_input)


def read_tool_input_or_none(stream: TextIO = sys.stdin) -> dict[str, Any] | None:
    """Advisory wrapper around ``read_tool_input`` that returns ``None`` on error.

    Intended for hooks that must fail open: any parse or contract violation
    silently returns ``None`` so the hook can exit 0 without blocking workflow.

    Args:
        stream: Readable text stream to parse (defaults to ``sys.stdin``).

    Returns:
        The ``tool_input`` mapping, or ``None`` if the input violates the contract.
    """
    try:
        return read_tool_input(stream)
    except StdinContractError:
        return None


def full_payload(stream: TextIO = sys.stdin) -> dict[str, Any]:
    """Parse the full hook payload from stdin, requiring it to be a JSON object.

    Unlike ``read_tool_input``, this returns the entire payload dict (including
    ``tool_name``, ``tool_input``, and any other keys), for hooks that need to
    inspect ``tool_name`` or other top-level fields.

    Args:
        stream: Readable text stream to parse (defaults to ``sys.stdin``).

    Returns:
        The full hook payload as a dict.

    Raises:
        StdinContractError: If stdin is not valid JSON or not an object.
    """
    raw = stream.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError) as exc:
        raise StdinContractError(f"stdin is not valid JSON: {exc}") from exc

    if not isinstance(data, Mapping):
        raise StdinContractError(
            f"stdin JSON must be an object (mapping), got {type(data).__name__}"
        )

    return dict(data)


def full_payload_or_none(stream: TextIO = sys.stdin) -> dict[str, Any] | None:
    """Advisory wrapper around ``full_payload`` that returns ``None`` on error.

    Args:
        stream: Readable text stream to parse (defaults to ``sys.stdin``).

    Returns:
        The full payload dict, or ``None`` if the input violates the contract.
    """
    try:
        return full_payload(stream)
    except StdinContractError:
        return None
