#!/usr/bin/env bash
# artifact-ledger.sh — PostToolUse Write (observer, NEVER blocks)
#
# Records ephemeral-artifact writes so a later session can find/garbage-collect
# them. Matches tool_input.file_path against:
#   - paths containing /plans/ or /specs/ (also relative "plans/…", "specs/…")
#   - basename containing "brainstorm" or "handoff" (case-insensitive)
#   - anything under $HOME/.claude/plans/
# EXCLUDED (never ledgered): .planning/ (do not ledger the ledger),
# dashboard/, .git/.
#
# Appends a JSONL line {ts, path, session_id} to
# <repo_root>/.planning/auto-pilot/session-artifacts.jsonl, where repo_root is
# found by walking up from CWD looking for .planning (like creation-gate.sh);
# if none found anywhere, mkdir -p at CWD/.planning/auto-pilot.
#
# PostToolUse observer: always exit 0, no stdout JSON. Errors / malformed
# stdin → silent exit 0, write nothing (fail-open).
set -euo pipefail

payload=$(cat)

printf '%s' "$payload" | python3 -c '
import json, os, sys
from datetime import datetime, timezone

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

try:
    file_path = (d.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        sys.exit(0)

    session_id = d.get("session_id") or ""

    norm = file_path.replace(os.sep, "/")
    low = norm.lower()
    base = os.path.basename(norm).lower()

    # EXCLUDE first: never ledger the ledger / dashboards / git internals.
    for seg in (".planning/", "dashboard/", ".git/"):
        if low.startswith(seg) or ("/" + seg) in low:
            sys.exit(0)

    home_plans = os.path.join(os.path.expanduser("~"), ".claude", "plans") + "/"
    abs_path = os.path.abspath(os.path.expanduser(norm))
    matched = (
        norm.startswith("plans/") or "/plans/" in norm
        or norm.startswith("specs/") or "/specs/" in norm
        or "brainstorm" in base   # case-insensitive basename match
        or "handoff" in base      # case-insensitive basename match
        or abs_path.startswith(home_plans)
    )
    if not matched:
        sys.exit(0)

    # Find repo root: walk up from CWD looking for .planning (creation-gate.sh
    # pattern, 5 levels). Not found anywhere -> CWD.
    cwd = os.getcwd()
    repo_root = cwd
    candidate = cwd
    for _ in range(5):
        if os.path.isdir(os.path.join(candidate, ".planning")):
            repo_root = candidate
            break
        parent = os.path.dirname(candidate)
        if parent == candidate:
            break
        candidate = parent

    ledger_dir = os.path.join(repo_root, ".planning", "auto-pilot")
    os.makedirs(ledger_dir, exist_ok=True)
    line = json.dumps(
        {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "path": file_path,
            "session_id": session_id,
        },
        ensure_ascii=False,
    )
    with open(
        os.path.join(ledger_dir, "session-artifacts.jsonl"), "a", encoding="utf-8"
    ) as f:
        f.write(line + "\n")
except Exception:
    pass
sys.exit(0)
' 2>/dev/null || true

exit 0
