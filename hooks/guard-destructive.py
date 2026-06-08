#!/usr/bin/env python3
"""PreToolUse hook — block unverified destructive Bash commands.

Reads a PreToolUse hook payload from stdin. If the tool is `Bash` and the
command matches one of the destructive patterns below, outputs a JSON
permissionDecision="deny" payload (with reason) so the harness blocks the
call and surfaces the explanation in the conversation.

Override path (intentional friction, not a bypass):
    1. Read the deny reason in the conversation.
    2. Verify the target manually (file path, table name, branch).
    3. If the destructive action is legitimate, create the marker file
       shown in the deny message:  touch /tmp/claude-destructive-approved-YYYYMMDD-HH.marker
    4. Retry — the hook then permits any pattern match for the rest of
       the current calendar hour. Marker auto-expires.

This hook fails OPEN: any internal exception (bad JSON, regex error, etc.)
exits 0 silently so workflow is never blocked by the hook itself crashing.

Implements CLAUDE.md §Destructive Action Protocol.
Add new patterns by appending (regex, reason) tuples to DESTRUCTIVE_PATTERNS.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

# (regex, human-readable reason). Each regex is matched case-insensitively
# against the full Bash command string.
DESTRUCTIVE_PATTERNS: list[tuple[str, str]] = [
    # ── File system ───────────────────────────────────────────
    (
        r"\brm\s+(?:-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|--recursive\s+--force|--force\s+--recursive)",
        "rm with combined -r/-f flags (recursive force delete)",
    ),
    (
        r"\bsudo\s+rm\b",
        "sudo rm (privileged file deletion)",
    ),
    (
        r"\bfind\b[^;|&]*\s-delete(?:\s|$|[;|&])",
        "find -delete (deletes matched files/directories)",
    ),
    (
        r"\bfind\b[^;|&]*\s-exec(?:dir)?\s+rm\s+(?:-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*|-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*|--recursive\s+--force|--force\s+--recursive|(?:-[a-zA-Z]*r[a-zA-Z]*|--recursive)\s+(?:-[a-zA-Z]*f[a-zA-Z]*|--force)|(?:-[a-zA-Z]*f[a-zA-Z]*|--force)\s+(?:-[a-zA-Z]*r[a-zA-Z]*|--recursive))(?:\s|$)",
        "find -exec rm with recursive force flags",
    ),
    (
        r"\bfind\b[^;|&]*\s-exec(?:dir)?\s+rm(?:\s|$)",
        "find -exec rm (deletes matched paths)",
    ),
    (
        r"\bfind\b[^;|&]*\|\s*xargs\b(?:\s+(?:-[^\s;|&]+|--[^\s;|&]+))*\s+rm(?:\s|$)",
        "find piped to xargs rm (deletes matched paths)",
    ),
    # ── Git history rewriting ─────────────────────────────────
    (
        r"\bgit\s+push\b[^;|&]*\s(?:--force(?!-with-lease)|-f)(?:\s|$)",
        "git push --force / -f (use --force-with-lease + explicit user approval instead)",
    ),
    (
        r"\bgit\s+reset\s+--hard\b",
        "git reset --hard (destroys uncommitted work in working tree)",
    ),
    (
        r"\bgit\s+clean\s+-[a-zA-Z]*f",
        "git clean -f (untracked files cannot be recovered)",
    ),
    (
        r"\bgit\s+branch\s+-D\b",
        "git branch -D (force delete may lose unmerged commits)",
    ),
    (
        r"--no-verify\b",
        "git --no-verify (bypasses pre-commit hooks)",
    ),
    (
        r"--no-gpg-sign\b",
        "git --no-gpg-sign (bypasses commit signing)",
    ),
    # ── SQL destructive statements ────────────────────────────
    (
        r"\bDROP\s+(TABLE|DATABASE|SCHEMA)\b",
        "SQL DROP statement",
    ),
    (
        r"\bTRUNCATE\s+(TABLE\s+)?[\w.\"`]+",
        "SQL TRUNCATE statement",
    ),
    (
        # \S+\b prevents backtracking past the full table token, so a
        # legitimate "DELETE FROM users WHERE id=1" doesn't shrink to
        # "DELETE FROM user" and slip past the negative lookahead.
        r"\bDELETE\s+FROM\s+\S+\b(?!\s+(?:WHERE|USING)\b)",
        "SQL DELETE FROM without WHERE clause",
    ),
    # ── Manual deploy paths ───────────────────────────────────
    (
        r"\bssh\s+[^\s]*@[^\s]+",
        "manual SSH to remote host (use CI/CD pipeline + gh run watch instead)",
    ),
    (
        r"\bscp\s+[^\s]*@[^\s]+:|\bscp\s+[^\s]+\s+[^\s]*@[^\s]+:",
        "manual SCP file transfer (use CI/CD pipeline instead)",
    ),
]


def respond_and_exit(decision: str, reason: str) -> None:
    """Emit a PreToolUse JSON response and exit cleanly."""
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    sys.exit(0)


# Match a `$(cat <<'TAG' ... TAG)` (or unquoted/double-quoted TAG) heredoc.
# Used to scrub commit message bodies before pattern matching, since the
# text inside a heredoc is data passed to git, not commands to execute.
_HEREDOC_RE = re.compile(
    r"\$\(\s*cat\s+<<-?\s*['\"]?(\w+)['\"]?\s*\n.*?\n\1\s*\n?\s*\)",
    re.DOTALL,
)

# Match a `-m "..."` or `-m '...'` flag (the standalone commit message form).
# Single-line strings only — multi-line bodies use the heredoc form above.
_DASH_M_RE = re.compile(r"-m\s+(?:'[^']*'|\"[^\"]*\")")


def scrub_text_arguments(command: str) -> str:
    """Strip git commit message bodies before pattern matching.

    Without this, every commit message that *documents* a destructive
    pattern (e.g. a CLAUDE.md change-log mentioning ``rm -rf``) would
    trip the guard, even though git commit -m takes data, not commands.
    SQL inside `mcpl call ... '{"query": "..."}'` is intentionally NOT
    stripped — that's a real execution path that should still be scanned.
    """
    command = _HEREDOC_RE.sub("$(cat <<'EOF'\nEOF\n)", command)
    command = _DASH_M_RE.sub("-m ''", command)
    return command


def _load_payload(raw: str) -> Mapping[str, Any] | None:
    try:
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, Mapping):
        return None
    return cast(Mapping[str, Any], data)


def _bash_command(data: Mapping[str, Any]) -> str | None:
    if data.get("tool_name") != "Bash":
        return None
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, Mapping):
        return None
    command = tool_input.get("command", "")
    return command if isinstance(command, str) and command else None


def _approval_marker(now: datetime) -> str:
    return os.path.join(
        tempfile.gettempdir(),
        f"claude-destructive-approved-{now.strftime('%Y%m%d-%H')}.marker",
    )


def _marker_valid(path: str, now: datetime) -> bool:
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        return (
            mtime.year == now.year
            and mtime.month == now.month
            and mtime.day == now.day
            and mtime.hour == now.hour
        )
    except OSError:
        return False


def _respond_to_match(reason: str, marker: str, now: datetime) -> None:
    if os.path.isfile(marker) and _marker_valid(marker, now):
        respond_and_exit(
            "allow",
            f"destructive pattern matched ({reason}) but evidence marker present at {marker} — proceeding.",
        )
    respond_and_exit(
        "deny",
        (
            f"BLOCKED: {reason}. "
            f"Per CLAUDE.md §Destructive Action Protocol, verify the target "
            f"first (read the file, SELECT COUNT(*), check the branch). "
            f"After explicit user approval, override with: touch {marker}"
        ),
    )


def _scan_destructive_patterns(scanned: str, marker: str, now: datetime) -> None:
    for pattern, reason in DESTRUCTIVE_PATTERNS:
        try:
            matched = re.search(pattern, scanned, re.IGNORECASE)
        except re.error:
            continue
        if matched:
            _respond_to_match(reason, marker, now)


def main() -> None:
    """Run the guard-destructive command-line entry point."""
    payload = _load_payload(sys.stdin.read())
    if payload is None:
        sys.exit(0)
    command = _bash_command(payload)
    if command is None:
        sys.exit(0)
    now = datetime.now()
    scanned = scrub_text_arguments(command)
    _scan_destructive_patterns(scanned, _approval_marker(now), now)
    sys.exit(0)


if __name__ == "__main__":
    main()
