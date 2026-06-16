#!/usr/bin/env python3
"""PreToolUse hook — enforce codex-orchestra conductor mode per repo.

Hard mechanism behind the `/codex-orchestra` skill's optional enforcement. When a
repo opts in by placing a `.codex-conductor` marker file at its root, Claude must
NOT write implementation source or test code itself — that work is delegated to
Codex. This hook blocks Edit/Write/MultiEdit/NotebookEdit on code+test files in
such repos and points back to /codex-orchestra.

Opt-in is per repo: create the marker to enable, delete it to disable.
    touch <repo-root>/.codex-conductor      # enable conductor enforcement
    rm    <repo-root>/.codex-conductor      # disable

Always allowed (so the conductor can still do its own job): Markdown/docs/text,
anything under a `plans/` directory, dotfiles, and the marker itself. Only known
source/test code extensions are blocked.

Fails OPEN: any internal error exits 0 silently so the hook never blocks work by
crashing. Implements the codex-orchestra SKILL.md "Per-project enforcement (v2)".
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _stdin_contract import full_payload_or_none  # noqa: E402

MARKER = ".codex-conductor"

# Known source/test code extensions that Codex (not Claude) must author.
CODE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".rs",
    ".java", ".kt", ".kts", ".rb", ".php", ".c", ".h", ".cc", ".cpp", ".cxx",
    ".hpp", ".hh", ".cs", ".swift", ".m", ".mm", ".scala", ".ex", ".exs",
    ".clj", ".cljs", ".vue", ".svelte", ".dart", ".lua", ".pl", ".r",
    ".sh", ".bash", ".zsh", ".fish", ".sql", ".proto", ".gradle",
}

# Extensions/paths always allowed even under conductor mode.
DOC_EXTS = {".md", ".markdown", ".mdx", ".txt", ".rst", ".adoc"}


def respond_and_exit(decision: str, reason: str) -> None:
    """Provide the public respond and exit API."""
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


def find_marker_root(start: str) -> str | None:
    """Walk up from `start` to filesystem root looking for the marker.

    Returns the directory containing the marker (the repo root), or None.
    Callers use this to scope path checks like `plans/` to inside the repo,
    rather than matching any ancestor directory that happens to be named the
    same.
    """
    cur = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(cur, MARKER)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _target_path(data: Mapping[str, Any]) -> str | None:
    if data.get("tool_name", "") not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        return None
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, Mapping):
        return None
    value = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    return value if isinstance(value, str) and value else None


def _marker_root(data: Mapping[str, Any], fpath: str) -> str | None:
    cwd = data.get("cwd")
    fallback = cwd if isinstance(cwd, str) else os.getcwd()
    search_root = os.path.dirname(os.path.abspath(fpath)) or fallback
    return find_marker_root(search_root)


def _repo_rel_parts(fpath: str, marker_root: str) -> list[str]:
    try:
        rel = os.path.relpath(os.path.abspath(fpath), marker_root)
    except ValueError:
        return []
    return rel.split(os.sep) if rel else []


def _always_allowed(fpath: str, marker_root: str) -> bool:
    base = os.path.basename(fpath)
    ext = os.path.splitext(fpath)[1].lower()
    if base == MARKER or ext in DOC_EXTS:
        return True
    rel_parts = _repo_rel_parts(fpath, marker_root)
    return bool(rel_parts and rel_parts[0] == "plans")


def main() -> None:
    """Run the codex-conductor-guard command-line entry point."""
    data = full_payload_or_none(sys.stdin)
    if data is None:
        sys.exit(0)
    fpath = _target_path(data)
    if fpath is None:
        sys.exit(0)
    marker_root = _marker_root(data, fpath)
    if not marker_root or _always_allowed(fpath, marker_root):
        sys.exit(0)
    if os.path.splitext(fpath)[1].lower() in CODE_EXTS:
        respond_and_exit(
            "deny",
            f"Conductor mode active ({MARKER} present): Claude must not write implementation/test code itself. Delegate this edit to Codex via /codex-orchestra (Codex writes code through `codex-companion task --write`; you plan, review, and gate). To disable enforcement for this repo, delete the {MARKER} marker.",
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
