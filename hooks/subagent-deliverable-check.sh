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
for p in missing:
    print(
        f"[subagent-deliverable-check] WARNING: subagent claimed to write \x27{p}\x27 "
        f"but path does not exist on disk.",
        file=sys.stderr,
    )

# --- Check (a): DONE-without-verify-evidence ---
# If the report claims DONE but carries no verify-log SHA-256, warn.
# A valid SHA-256 is 64 lowercase hex chars.  Only match a 64-hex that
# appears on a line containing a "Verify log SHA-256:" label (case-insensitive,
# bold markers allowed).  Bare hex tokens anywhere in the report do NOT count
# — they are too broad and suppress the warning on stray content hashes,
# diff identifiers, or context-bundle SHAs.
DONE_STATUS_RE = re.compile(
    r"^\*{0,2}Status\*{0,2}:?\*{0,2}\s*\*{0,2}DONE\*{0,2}\s*$",
    re.IGNORECASE | re.MULTILINE,
)
SHA256_RE = re.compile(
    r"^\*{0,2}Verify\s+log\s+SHA-?256\*{0,2}\s*:.*\b([0-9a-f]{64})\b",
    re.IGNORECASE | re.MULTILINE,
)

is_done = bool(DONE_STATUS_RE.search(output_text))
has_sha = bool(SHA256_RE.search(output_text))

if is_done and not has_sha:
    print(
        "[subagent-deliverable-check] WARNING: report marked DONE but carries no"
        " verify-log SHA-256 (worker.md rule 9) — verify evidence missing;"
        " re-verify before trusting \x27completed\x27.",
        file=sys.stderr,
    )

# --- Check (b): tests-required-but-untouched ---
# Best-effort: only fires when AUTO_PILOT_SCOPE_FILES env var is set and
# includes a test-file path segment.  If the DONE report changes no test
# file, warn.
scope_files = os.environ.get("AUTO_PILOT_SCOPE_FILES", "")
if is_done and scope_files:
    TEST_PATH_RE = re.compile(
        r"(?:^|[\s,:/])tests/|test_[^/\s,]+\.py|[^/\s,]+_test\.py",
        re.IGNORECASE,
    )
    scope_has_tests = bool(TEST_PATH_RE.search(scope_files))
    if scope_has_tests:
        # Only look for test paths inside structured sections of the report:
        #   1. The "Files changed:" block — lines from that header until the
        #      next blank line or next bold header.
        #   2. "+++ b/..." lines inside a ```diff``` fenced block.
        # Prose mentions (e.g. "I did NOT touch tests/test_foo.py") must NOT
        # suppress the warning — they are too imprecise.
        files_changed_block = re.search(
            r"\*{0,2}Files\s+changed\*{0,2}:?\*{0,2}[^\n]*\n((?:[^\n]+\n)*?)(?:\n|\*{2}|\Z)",
            output_text,
            re.IGNORECASE,
        )
        files_section = files_changed_block.group(0) if files_changed_block else ""
        diff_plus_lines = "\n".join(
            line for line in output_text.splitlines() if line.startswith("+++ b/")
        )
        report_has_test = bool(
            TEST_PATH_RE.search(files_section) or TEST_PATH_RE.search(diff_plus_lines)
        )
        if not report_has_test:
            print(
                "[subagent-deliverable-check] WARNING: contract scope includes test"
                " files but the DONE report changed none — possible missing tests"
                " (worker.md rule 5).",
                file=sys.stderr,
            )

sys.exit(0)
' 2>&1 || true

exit 0
