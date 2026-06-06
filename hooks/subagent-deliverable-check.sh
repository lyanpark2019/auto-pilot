#!/usr/bin/env bash
# subagent-deliverable-check.sh — SubagentStop
#
# Advisory (non-blocking, exit 0 always): scan the subagent's final output
# for absolute file paths claimed as written/created; warn on stderr for any
# path that does not exist on disk.  Useful for catching subagents that
# hallucinate a deliverable write without actually touching the filesystem.
#
# Adapted from oh-my-claudecode deliverable-existence pattern.
#
# Stop-hook reentry guard: if stop_hook_active is true in the payload,
# exit immediately to avoid infinite hook re-invocation.
set -euo pipefail

payload=$(cat)

printf '%s' "$payload" | python3 -c '
import json
import os
import re
import sys

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

# Reentry guard: Claude sets stop_hook_active=true when a Stop/SubagentStop
# hook itself triggers another stop event.  Exit immediately to break the loop.
if d.get("stop_hook_active"):
    sys.exit(0)

# Extract the subagent'"'"'s last output text.  The SubagentStop payload shape
# (Claude Code >=0.2): {"stop_reason": "...", "result": {"output": "...", ...}}
output_text = ""
result = d.get("result") or {}
if isinstance(result, dict):
    output_text = result.get("output") or result.get("text") or ""
if not output_text:
    output_text = d.get("output") or d.get("text") or ""

if not isinstance(output_text, str) or not output_text.strip():
    sys.exit(0)

# Patterns that suggest a path was claimed as written/created.
# Matches: "wrote /path/to/file", "created /path/to/file",
#          "/path/to/file — written", "saved to /path/to/file", etc.
WRITE_VERB_RE = re.compile(
    r"(?:(?:wrote?|created?|saved?(?:\s+to)?|written\s+to|generated?|output(?:ted)?)\s+(/[^\s,\x27\")\]]+))"
    r"|"
    r"(?:(/[^\s,\x27\")\]]+)\s+(?:—|-+)\s+(?:written|created|saved|generated))",
    re.IGNORECASE,
)

claimed_paths = []
for m in WRITE_VERB_RE.finditer(output_text):
    p = m.group(1) or m.group(2)
    if p and p not in claimed_paths:
        claimed_paths.append(p)

missing = [p for p in claimed_paths if not os.path.exists(p)]
if not missing:
    sys.exit(0)

for p in missing:
    print(
        f"[subagent-deliverable-check] WARNING: subagent claimed to write \x27{p}\x27 "
        f"but path does not exist on disk.",
        file=sys.stderr,
    )
sys.exit(0)
' 2>&1 || true

exit 0
