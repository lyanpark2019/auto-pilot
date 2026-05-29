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


def main() -> None:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name", "")
    if tool not in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        sys.exit(0)

    ti = data.get("tool_input") or {}
    fpath = ti.get("file_path") or ti.get("notebook_path") or ""
    if not fpath:
        sys.exit(0)

    # Enforcement only applies in a repo that opted in via the marker. Search
    # from the target file's directory (falls back to cwd).
    search_root = os.path.dirname(os.path.abspath(fpath)) or data.get("cwd") or os.getcwd()
    marker_root = find_marker_root(search_root)
    if not marker_root:
        sys.exit(0)

    base = os.path.basename(fpath)
    ext = os.path.splitext(fpath)[1].lower()

    # Always-allowed: the marker, docs/text, and `plans/` artifacts INSIDE the
    # marker repo. `plans` as an ancestor of the repo (e.g. `~/plans/myrepo/`)
    # must NOT bypass enforcement — that was the old bug.
    if base == MARKER or ext in DOC_EXTS:
        sys.exit(0)
    try:
        rel = os.path.relpath(os.path.abspath(fpath), marker_root)
    except ValueError:
        rel = ""
    rel_parts = rel.split(os.sep) if rel else []
    if rel_parts and rel_parts[0] == "plans":
        sys.exit(0)

    if ext in CODE_EXTS:
        respond_and_exit(
            "deny",
            (
                f"Conductor mode active ({MARKER} present): Claude must not write "
                f"implementation/test code itself. Delegate this edit to Codex via "
                f"/codex-orchestra (Codex writes code through `codex-companion task "
                f"--write`; you plan, review, and gate). To disable enforcement for "
                f"this repo, delete the {MARKER} marker."
            ),
        )

    # Non-code, non-doc files (configs, data, etc.) pass through.
    sys.exit(0)


if __name__ == "__main__":
    main()
