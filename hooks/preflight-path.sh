#!/usr/bin/env bash
# auto-pilot preflight: validate working dir and critical paths.
# Runs on SessionStart. Non-blocking — prints warnings to stderr but exits 0.
# Fires from /insights friction class: path typos (Valut/, /tmp, missing vault).

set -uo pipefail

cwd="$(pwd)"
warnings=()

# Rule 1: never in /tmp for a real project
case "$cwd" in
  /tmp|/tmp/*|/var/folders/*|/private/var/folders/*|/private/tmp|/private/tmp/*)
    warnings+=("auto-pilot: CWD is in $cwd — vault/spec ops will fail. cd to a real project root first.")
    ;;
esac

# Rule 2: if .planning/auto-pilot/state.json exists, project is mid-loop
if [[ -f .planning/auto-pilot/state.json ]]; then
  status=$(grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' .planning/auto-pilot/state.json 2>/dev/null | head -1 | sed 's/.*"\([^"]*\)"$/\1/')
  phase=$(grep -o '"current_phase"[[:space:]]*:[[:space:]]*[0-9]*' .planning/auto-pilot/state.json 2>/dev/null | head -1 | grep -o '[0-9]*')
  if [[ "$status" == "running" ]]; then
    echo "auto-pilot: resuming session — current_phase=$phase status=running" >&2
  fi
fi

# Rule 3: obsidian vault canonical path (per CLAUDE.md addition from insights)
# If user references a vault, prefer ~/Obsidian/AI-Vault or ~/Documents/Obsidian/AI-Vault
# Warn on common typos: Valut, Volt
if [[ -d ./Valut ]] || [[ -d ./Volt ]]; then
  warnings+=("auto-pilot: found typo'd vault dir (Valut/Volt) — canonical path is Obsidian/AI-Vault/")
fi

if [[ ${#warnings[@]} -gt 0 ]]; then
  for w in "${warnings[@]}"; do echo "$w" >&2; done
fi

# Rule 4: handoff pickup — walk up for .planning/auto-pilot/handoff-next.md.
# If found with frontmatter status: pending AND written_at < 7 days old:
#   - emit first 6000 chars as SessionStart additionalContext JSON on stdout
#   - flip frontmatter to status: consumed + consumed_at: <ISO>
# Stale (>7d), consumed, or malformed → silent skip. Fail-open everywhere.
handoff_file=""
walk_dir="$cwd"
while :; do
  if [[ -f "$walk_dir/.planning/auto-pilot/handoff-next.md" ]]; then
    handoff_file="$walk_dir/.planning/auto-pilot/handoff-next.md"
    break
  fi
  [[ "$walk_dir" == "/" ]] && break
  walk_parent="$(dirname "$walk_dir")"
  [[ "$walk_parent" == "$walk_dir" ]] && break
  walk_dir="$walk_parent"
done

if [[ -n "$handoff_file" ]] && command -v python3 >/dev/null 2>&1; then
  AUTO_PILOT_HANDOFF_FILE="$handoff_file" python3 - <<'PY' 2>/dev/null || true
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

path = os.environ.get("AUTO_PILOT_HANDOFF_FILE", "")
try:
    text = open(path, encoding="utf-8").read()
except Exception:
    sys.exit(0)

m = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(\n|\Z)", text, re.DOTALL)
if not m:
    sys.exit(0)  # malformed/missing frontmatter -> silent skip
fm = m.group(1)


def field(name: str) -> str:
    fmatch = re.search(r"^" + name + r":[ \t]*(.+?)[ \t]*$", fm, re.MULTILINE)
    return fmatch.group(1) if fmatch else ""


status = field("status")

# Derive this session's ID.  Claude passes session_id in the hook stdin JSON
# payload; we read it from the file descriptor the shell already consumed, so
# instead we fall back to a stable per-process identifier (PPID + path hash).
# The actual stdin payload is gone by this point (consumed by the bash here-doc
# redirect), so we synthesise an ID from environment + process context.
import hashlib

raw_env_sid = os.environ.get("CLAUDE_SESSION_ID", "") or ""
if raw_env_sid:
    current_session_id = raw_env_sid
else:
    ppid = str(os.getppid())
    raw = (ppid + "|" + path).encode("utf-8", errors="replace")
    current_session_id = "ppid-" + hashlib.sha256(raw).hexdigest()[:16]

consumed_by = field("consumed_by_session_id")

# Allow injection when:
#   a) status is pending (fresh, not yet consumed), OR
#   b) status is consumed AND consumed_by matches this session (restart replay)
if status == "consumed":
    if consumed_by and consumed_by == current_session_id:
        pass  # this session already consumed — re-inject for restart safety
    else:
        sys.exit(0)  # consumed by a different session -> silent skip
elif status != "pending":
    sys.exit(0)  # unknown status -> silent skip

raw_ts = field("written_at").strip("\"'")
try:
    ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
except Exception:
    sys.exit(0)  # unparseable written_at -> silent skip
if ts.tzinfo is None:
    ts = ts.replace(tzinfo=timezone.utc)
if datetime.now(timezone.utc) - ts > timedelta(days=7):
    sys.exit(0)  # stale -> silent skip

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": text[:6000],
    }
}))

if status != "pending":
    # Already consumed by this session; skip the flip (idempotent).
    sys.exit(0)

# Flip pending -> consumed, recording which session consumed it.
# The flip is written atomically via rename so a concurrent session
# cannot observe a half-written file.
import tempfile

now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
new_fm = re.sub(
    r"^status:[ \t]*pending[ \t]*$",
    (
        "status: consumed\n"
        "consumed_at: " + now_iso + "\n"
        "consumed_by_session_id: " + current_session_id
    ),
    fm,
    count=1,
    flags=re.MULTILINE,
)
new_text = "---\n" + new_fm + "\n---\n" + text[m.end():]
try:
    dir_ = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".handoff-next-tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        os.rename(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
except Exception:
    pass
PY
fi

exit 0
