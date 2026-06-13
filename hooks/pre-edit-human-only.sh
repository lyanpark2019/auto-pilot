#!/usr/bin/env bash
# ⓓ-1 pre-edit-human-only.sh — PreToolUse Edit|Write|MultiEdit
# Deny edits to paths/files that are human-only.
#
# Three protection tiers:
#   (a) Paths listed in .claude/human-only.paths (one path-prefix per line, # comments)
#   (b) Files with a "marker-led" line: after an optional comment opener
#       (one of  #  //  /*  *  ;  --  <!--  ) and whitespace, the line's FIRST
#       token is the HUMAN-ONLY marker. A trailing note or comment closer after
#       the marker is allowed. A mere inline mention buried in prose / a JSON
#       "description" does NOT self-protect -- otherwise this hook's own wiring
#       (hooks.json) self-locks on its description text. Fail-safe: a marker-led
#       line denies even when its comment is unterminated (errs toward protect).
#   (c) Tier-2 hardcoded core: schemas/, hooks/guard-*, and the two governance SoT pages
#
# Bypass: AUTO_PILOT_ALLOW_CORE_EDIT=1 overrides tier-2 only (logs allow reason).
# Unparseable stdin → allow (fail-open repo convention).
set -euo pipefail

# ── Tier-2 hardcoded paths (authoritative; .claude/human-only.paths lists them informally) ──
TIER2_PREFIXES=(
  "schemas/"
  "hooks/guard-"
  "docs/architecture.md"
  "skills/doc-management/references/doc-management-system.md"
)

deny() {
  local reason="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
    "${reason//\"/\\\"}"
  exit 0
}

payload=$(cat)

file_path=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("file_path") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")

if [[ -z "$file_path" ]]; then
  # Distinguish: truly unparseable stdin (fail-open advisory) vs valid payload
  # with no file_path key (legit non-edit tool call — silent allow).
  if ! printf '%s' "$payload" | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null; then
    printf '[hook:pre-edit-human-only] fail-open: unparseable stdin\n' >&2
  fi
  exit 0
fi

# Locate repo root (walk up from CWD looking for .claude/human-only.paths)
repo_root="$(pwd)"
candidate="$repo_root"
for _ in 1 2 3 4 5; do
  if [[ -f "$candidate/.claude/human-only.paths" ]]; then
    repo_root="$candidate"
    break
  fi
  candidate="$(dirname "$candidate")"
done

# ── Tier (c): tier-2 hardcoded core ──
# Anchored to THIS plugin's root (review r1: bare substring */schemas/* match
# false-denied any target repo's schemas/ dir — auto-pilot's core cross-repo
# edit use case). Relative paths resolve against CWD before comparison.
plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
abs_path="$file_path"
[[ "$abs_path" != /* ]] && abs_path="$(pwd)/$abs_path"
# Canonicalize ./ .. and symlinks (r2 review: lexical compare was bypassable
# via `schemas/../schemas/x` or a symlink into the plugin). realpath works for
# not-yet-existing files too (resolves the existing prefix lexically+symlink).
abs_path="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$abs_path" 2>/dev/null || printf '%s' "$abs_path")"
for prefix in "${TIER2_PREFIXES[@]}"; do
  if [[ "$abs_path" == "$plugin_root/$prefix"* ]]; then
    if [[ "${AUTO_PILOT_ALLOW_CORE_EDIT:-0}" == "1" ]]; then
      echo "auto-pilot: ALLOW tier-2 core edit (AUTO_PILOT_ALLOW_CORE_EDIT=1): $file_path" >&2
    else
      deny "Tier-2 core protected path: $file_path — set AUTO_PILOT_ALLOW_CORE_EDIT=1 to override"
    fi
    break
  fi
done

# ── Tier (a): .claude/human-only.paths prefixes ──
human_only_file="$repo_root/.claude/human-only.paths"
if [[ -f "$human_only_file" ]]; then
  while IFS= read -r line; do
    # Skip blank lines and comments
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ "$file_path" == "$line"* ]] || [[ "$file_path" == *"/$line"* ]]; then
      deny "Path is listed in .claude/human-only.paths ($line): $file_path"
    fi
  done < "$human_only_file"
fi

# ── Tier (b): file contains HUMAN-ONLY marker ──
# Resolve target file: check as absolute, then relative to repo_root, then CWD
target_file=""
if [[ -f "$file_path" ]]; then
  target_file="$file_path"
elif [[ -f "$repo_root/$file_path" ]]; then
  target_file="$repo_root/$file_path"
fi

if [[ -n "$target_file" ]]; then
  if grep -qE '^[[:space:]]*(#|//|/\*|\*|;|--|<!--)?[[:space:]]*HUMAN-ONLY(-->|\*/)?([[:space:]].*)?$' "$target_file" 2>/dev/null; then
    deny "File contains HUMAN-ONLY marker: $file_path"
  fi
fi

exit 0
