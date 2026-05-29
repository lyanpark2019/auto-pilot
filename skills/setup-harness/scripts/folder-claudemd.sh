#!/usr/bin/env bash
# Folder-level CLAUDE.md interface generator + candidate detector.
#
# A "candidate" folder holds >= FOLDER_THRESHOLD (default 10) source files,
# excluding vendor/build/hidden trees. These are the folders Step 2 of the
# skill wants a <=10-line local interface in (layer boundaries, dense modules).
#
# Subcommands:
#   folder-claudemd.sh candidates   # print candidate dirs, one per line
#   folder-claudemd.sh coverage     # print "<covered> <total>" (folders with CLAUDE.md / all candidates)
#   folder-claudemd.sh scaffold     # create a <=10-line CLAUDE.md in each candidate lacking one
#
# Honors DRY_RUN=1 (scaffold prints intent, writes nothing).
# bash 3.2 compatible (no assoc arrays, no ${!arr[@]}).
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$ROOT" || exit 1
THRESHOLD="${FOLDER_THRESHOLD:-10}"
DRY_RUN="${DRY_RUN:-0}"

list_candidates() {
  find . -type f \
    \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \
       -o -name '*.go' -o -name '*.rs' -o -name '*.swift' -o -name '*.kt' \
       -o -name '*.rb' -o -name '*.java' -o -name '*.cs' \) \
    -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/.venv/*' \
    -not -path '*/venv/*' -not -path '*/dist/*' -not -path '*/build/*' \
    -not -path '*/__pycache__/*' -not -path '*/.next/*' -not -path '*/target/*' \
    -not -path '*/vendor/*' -not -path '*/.claude/*' 2>/dev/null \
  | sed 's#/[^/]*$##' | sort | uniq -c \
  | while read -r count dir; do
      [ "$count" -ge "$THRESHOLD" ] && [ "$dir" != "." ] && echo "$dir"
    done
}

# Exact placeholder tokens the scaffold emits. A folder counts as "covered"
# only when ALL of these are gone (i.e. the stub was actually filled in).
# Matching exact tokens — not a loose `{[a-z]` pattern — so a real doc that
# legitimately contains `${var}` or `{type}` is NOT mis-flagged as a stub.
#
# Single source of truth: these three placeholders are emitted by scaffold() AND
# checked by is_substantive(). Edit them here only — both sides stay in sync.
PH_PROHIBITION='{prohibition}'
PH_REASON='{reason, link to ADR-NNN}'
PH_CONVENTION='{local convention the agent must follow inside this folder}'

is_substantive() {
  [ -f "$1" ] || return 1
  for marker in "$PH_PROHIBITION" "$PH_REASON" "$PH_CONVENTION"; do
    grep -qF "$marker" "$1" && return 1   # an unfilled scaffold placeholder remains
  done
  return 0
}

coverage() {
  total=0; covered=0
  while IFS= read -r d; do
    [ -z "$d" ] && continue
    total=$((total + 1))
    is_substantive "$d/CLAUDE.md" && covered=$((covered + 1))
  done < <(list_candidates)
  echo "$covered $total"
}

scaffold() {
  while IFS= read -r d; do
    [ -z "$d" ] && continue
    f="$d/CLAUDE.md"
    if [ -f "$f" ]; then
      echo "  = $f (exists, skipped)"
      continue
    fi
    layer=$(basename "$d")
    if [ "$DRY_RUN" = "1" ]; then
      echo "  [dry-run] would create $f"
      continue
    fi
    cat > "$f" <<EOF
# ${layer}/ — local interface

> Folder-level rules for \`${d#./}\`. Keep <=10 lines. Root contract: see nearest parent CLAUDE.md.

## 절대 금지 (Prohibitions)
- **{prohibition}** — {reason, link to ADR-NNN}

## Notes
- {local convention the agent must follow inside this folder}
EOF
    echo "  + $f (edit before commit)"
  done < <(list_candidates)
}

case "${1:-scaffold}" in
  candidates) list_candidates ;;
  coverage)   coverage ;;
  scaffold)   scaffold ;;
  *) echo "usage: folder-claudemd.sh {candidates|coverage|scaffold}" >&2; exit 1 ;;
esac
