#!/usr/bin/env bash
# sync-to-codex.sh — one-way deploy of versioned Codex CLI skills out of this repo.
#
# SOURCE OF TRUTH = this repo (codex/skills/*). DEPLOY TARGET = ~/.codex/skills/.
# Edit skills HERE, then run this script. Never hand-edit the deployed copies.
#
# Safety contract:
#   - Per-skill rsync: --delete applies ONLY INSIDE each managed skill dir, so a
#     stale file removed from the repo also disappears from the deployed copy.
#   - The destination PARENT is never pruned: unmanaged skills and symlinks in
#     ~/.codex/skills/ (defuddle, sportic-contents, design-md -> ..., etc.) survive.
#   - __pycache__/, *.pyc, .DS_Store are never shipped (and, being excluded, are
#     not deleted from the destination either).
#
# Usage:
#   ./sync-to-codex.sh             sync all managed skills
#   ./sync-to-codex.sh --dry-run   show the per-skill rsync plan; change nothing
#   ./sync-to-codex.sh -d|--diff   report repo<->deployed drift; no sync;
#                                  exit 1 if drift found (usable as a check)
#   ./sync-to-codex.sh -h|--help   this text
#
# Env: CODEX_SKILLS_DIR overrides the destination (default: $HOME/.codex/skills).
# Exit codes: 0 ok / no drift · 1 drift found or validation failure · 2 usage error.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_ROOT="$SCRIPT_DIR/skills"
DEST_ROOT="${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"

RSYNC_EXCLUDES=(--exclude '__pycache__/' --exclude '*.pyc' --exclude '.DS_Store')

usage() {
  # Print the comment header (everything between the shebang and the first
  # non-comment line), stripped of the leading "# ".
  awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
}

MODE="sync"
if [ "$#" -gt 1 ]; then
  echo "ERROR: at most one argument expected." >&2
  usage >&2
  exit 2
fi
case "${1:-}" in
  "") MODE="sync" ;;
  --dry-run) MODE="dry-run" ;;
  -d|--diff) MODE="diff" ;;
  -h|--help) usage; exit 0 ;;
  *)
    echo "ERROR: unknown argument: $1" >&2
    usage >&2
    exit 2
    ;;
esac

# Drop attribute-only itemize lines for the skill root dir ("./") — pure noise
# (e.g. GNU rsync directory-mtime lines). File/deletion lines always carry a name.
filter_noise() {
  grep -vE '^\.d[^ ]* \./$' || true
}

# ---- pre-flight validation -------------------------------------------------
if [ ! -d "$SRC_ROOT" ]; then
  echo "ERROR: source dir not found: $SRC_ROOT" >&2
  exit 1
fi

SKILLS=()
MISSING_MANIFEST=()
for src in "$SRC_ROOT"/*/; do
  [ -d "$src" ] || continue
  name="$(basename "$src")"
  SKILLS+=("$name")
  [ -f "$src/SKILL.md" ] || MISSING_MANIFEST+=("$name")
done

if [ "${#SKILLS[@]}" -eq 0 ]; then
  echo "ERROR: no skill dirs under $SRC_ROOT — nothing to sync." >&2
  exit 1
fi
if [ "${#MISSING_MANIFEST[@]}" -gt 0 ]; then
  echo "ERROR: refusing to run — skill dir(s) missing SKILL.md:" >&2
  printf '  - %s\n' "${MISSING_MANIFEST[@]}" >&2
  exit 1
fi

if [ ! -d "$DEST_ROOT" ]; then
  if [ "$MODE" = "sync" ]; then
    mkdir -p "$DEST_ROOT"
  else
    echo "NOTE: destination $DEST_ROOT does not exist — every skill counts as drift."
  fi
fi

echo "mode=$MODE  skills=${#SKILLS[@]}  src=$SRC_ROOT  dest=$DEST_ROOT"

# ---- per-skill loop ----------------------------------------------------------
DRIFTED=0
for name in "${SKILLS[@]}"; do
  src="$SRC_ROOT/$name/"
  dest="$DEST_ROOT/$name/"

  case "$MODE" in
    diff|dry-run)
      if [ ! -d "$DEST_ROOT" ] || [ ! -d "$dest" ]; then
        DRIFTED=$((DRIFTED + 1))
        if [ "$MODE" = "diff" ]; then
          echo "DRIFT $name: missing at destination (sync would create it)"
        else
          echo "WOULD SYNC $name: missing at destination (sync would create it)"
        fi
        continue
      fi
      changes="$(rsync -ani --delete "${RSYNC_EXCLUDES[@]}" "$src" "$dest" | filter_noise)"
      if [ -n "$changes" ]; then
        DRIFTED=$((DRIFTED + 1))
        if [ "$MODE" = "diff" ]; then
          echo "DRIFT $name:"
        else
          echo "WOULD SYNC $name:"
        fi
        printf '%s\n' "$changes" | sed 's/^/    /'
      else
        echo "ok    $name"
      fi
      ;;
    sync)
      rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$src" "$dest"
      echo "synced $name"
      ;;
  esac
done

# ---- summary -----------------------------------------------------------------
case "$MODE" in
  diff)
    if [ "$DRIFTED" -gt 0 ]; then
      echo "RESULT: $DRIFTED/${#SKILLS[@]} skill(s) drifted — run $(basename "${BASH_SOURCE[0]}") to deploy the repo state."
      exit 1
    fi
    echo "RESULT: no drift — deployed copies match the repo."
    ;;
  dry-run)
    echo "RESULT: dry-run only — $DRIFTED/${#SKILLS[@]} skill(s) would change; nothing was written."
    ;;
  sync)
    echo "RESULT: ${#SKILLS[@]} skill(s) synced to $DEST_ROOT (unmanaged neighbors untouched)."
    ;;
esac
