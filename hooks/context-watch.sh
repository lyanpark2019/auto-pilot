#!/usr/bin/env bash
# context-watch.sh — UserPromptSubmit
#
# Estimates context usage from the transcript file SIZE and, once past a
# threshold, injects a one-time nudge to run `/auto-pilot handoff` so the
# next-session handoff gets written BEFORE the context window fills up.
#
# HEURISTIC ASSUMPTION (documented, not a token count):
#   estimated tokens ~= transcript_bytes / 8
# The transcript is JSONL — JSON escaping + per-message metadata + tool
# results inflate byte count well past model-visible text (plain English is
# ~4 bytes/token; JSONL overhead roughly doubles that). 8 bytes/token is the
# calibrated-conservative divisor: it UNDER-estimates tokens, so the warning
# fires late rather than spamming early.
#
# Threshold = AUTO_PILOT_CONTEXT_LIMIT_TOKENS (default 200000)
#             x AUTO_PILOT_HANDOFF_PCT (default 40) / 100.
# Once-per-session: marker $TMPDIR/auto-pilot-ctxwarn-<session_id>.marker.
# Marker present / below threshold / no transcript / malformed stdin
#   -> silent exit 0 (fail-open, never blocks the prompt).
set -euo pipefail

payload=$(cat)

printf '%s' "$payload" | python3 -c '
import json, os, sys, tempfile

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

try:
    transcript = d.get("transcript_path") or ""
    if not transcript or not os.path.isfile(transcript):
        sys.exit(0)

    size = os.path.getsize(transcript)
    est_tokens = size / 8  # see heuristic assumption in the header comment

    def _env_int(name, default):
        try:
            return int(os.environ.get(name, "") or default)
        except (TypeError, ValueError):
            return default

    limit = _env_int("AUTO_PILOT_CONTEXT_LIMIT_TOKENS", 200000)
    pct = _env_int("AUTO_PILOT_HANDOFF_PCT", 40)
    if limit <= 0 or pct <= 0:
        sys.exit(0)
    threshold = limit * pct / 100

    if est_tokens <= threshold:
        sys.exit(0)

    session_id = d.get("session_id") or ""
    # Sanitize: session_id lands in a filename — strip path-capable chars.
    safe_sid = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    tmpdir = os.environ.get("TMPDIR") or tempfile.gettempdir()
    marker = os.path.join(tmpdir, "auto-pilot-ctxwarn-" + safe_sid + ".marker")

    if os.path.exists(marker):
        sys.exit(0)  # already warned this session

    # Create marker BEFORE emitting so a crash after this point cannot spam.
    with open(marker, "w", encoding="utf-8") as f:
        f.write(str(int(est_tokens)))

    used_pct = round(est_tokens / limit * 100)
    msg = (
        "[context-watch] estimated context ~{}% "
        "(heuristic from transcript size) — consider `/auto-pilot handoff` "
        "to write the next-session handoff now."
    ).format(used_pct)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": msg,
        }
    }))
except Exception:
    pass
sys.exit(0)
' 2>/dev/null || true

exit 0
