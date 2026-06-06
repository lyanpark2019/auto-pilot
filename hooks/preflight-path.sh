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


if field("status") != "pending":
    sys.exit(0)  # consumed (or unknown) -> silent skip

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

# Flip pending -> consumed (best-effort; emission already happened, fail-open).
now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
new_fm = re.sub(
    r"^status:[ \t]*pending[ \t]*$",
    "status: consumed\nconsumed_at: " + now_iso,
    fm,
    count=1,
    flags=re.MULTILINE,
)
try:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("---\n" + new_fm + "\n---\n" + text[m.end():])
except Exception:
    pass
PY
fi

exit 0
