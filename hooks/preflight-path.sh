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

exit 0
