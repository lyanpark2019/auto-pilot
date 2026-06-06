#!/usr/bin/env bash
# context-watch.sh — UserPromptSubmit
#
# Estimates context usage from the transcript file SIZE and, once past a
# threshold, injects a one-time nudge to run `/auto-pilot handoff` so the
# next-session handoff gets written BEFORE the context window fills up.
#
# HEURISTIC ASSUMPTION (documented, not a token count):
#   estimated tokens ~= transcript_bytes / 16
# Calibrated 2026-06-07 against 3 real auto-pilot transcripts
# (c17a..a6: 3.55 MB → ~211k tokens → divisor 16.8;
#  3e1d..58: 2.92 MB → ~122k tokens → divisor 23.8;
#  9e36..4a: 2.61 MB → ~112k tokens → divisor 23.3).
# Token estimate = extracted text content (content[].text + tool input strings) / 4.
# Divisor 16 is the p-low bound — errs toward firing slightly early rather than
# missing the window; prior value of 8 under-estimated by ~2x.
#
# Threshold = AUTO_PILOT_CONTEXT_LIMIT_TOKENS (default 200000)
#             x AUTO_PILOT_HANDOFF_PCT (default 40) / 100.
# Once-per-session: marker $TMPDIR/auto-pilot-ctxwarn-<marker_id>.marker.
# Marker ID = session_id when non-empty; falls back to PPID+transcript-path
# hash so two concurrent sessions never share a marker even if session_id
# is absent from the hook payload.
# Marker present / below threshold / no transcript / malformed stdin
#   -> silent exit 0 (fail-open, never blocks the prompt).
set -euo pipefail

payload=$(cat)

# shellcheck disable=SC2016  # single-quoted python3 -c body is intentional — no bash expansion wanted
printf '%s' "$payload" | python3 -c '
import hashlib, json, os, sys, tempfile

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)

try:
    transcript = d.get("transcript_path") or ""
    if not transcript or not os.path.isfile(transcript):
        sys.exit(0)

    size = os.path.getsize(transcript)
    est_tokens = size / 16  # see divisor calibration in the header comment

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
    if session_id:
        # Sanitize: session_id lands in a filename — strip path-capable chars.
        safe_sid = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
    else:
        # Deterministic fallback: PPID + transcript path so two concurrent
        # sessions never collide even when session_id is absent.
        ppid = str(os.getppid())
        raw = (ppid + "|" + transcript).encode("utf-8", errors="replace")
        safe_sid = "ppid-" + hashlib.sha256(raw).hexdigest()[:16]
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
