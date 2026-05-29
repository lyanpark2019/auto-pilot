#!/usr/bin/env bash
# check_doc_drift.sh — generic doc-citation drift detector for any project.
#
# Scans common doc roots (CLAUDE.md, README.md, docs/**/*.md, .claude/**/*.md,
# src/**/CLAUDE.md) for `path[:line]` citations. Verifies each cited path
# exists; if a line number is present, verifies the file has >=N lines.
#
# Resolution order for each citation:
#   1. ./foo, ../foo  -> relative to the doc's own directory
#   2. otherwise      -> repo root (first match wins)
#   3. otherwise      -> $DRIFT_FALLBACK_PREFIX/<path>   (env, e.g. "src/myproj")
#
# Exit 0 = clean, exit 1 = drift found (report on stdout).
# Pure grep + wc, <1s, no LLM cost. Bash 3.x compatible (macOS-safe).
#
# Designed to be copied verbatim into target repos as scripts/quality/check_doc_drift.sh
# and wired into pre-push via templates/lefthook.yml.drift-snippet.

set -eu
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

FALLBACK_PREFIX="${DRIFT_FALLBACK_PREFIX:-}"

# ---- collect doc files ------------------------------------------------------
doc_files=""
for root in CLAUDE.md README.md docs .claude; do
  if [ -f "$root" ]; then
    doc_files="$doc_files $root"
  elif [ -d "$root" ]; then
    while IFS= read -r f; do doc_files="$doc_files $f"; done \
      < <(find "$root" -type f -name '*.md' 2>/dev/null)
  fi
done
if [ -d src ]; then
  while IFS= read -r f; do doc_files="$doc_files $f"; done \
    < <(find src -type f -name 'CLAUDE.md' 2>/dev/null)
fi

# Citation regex — file-ish token with extension we care about, optional :line.
cite_re='[A-Za-z0-9_./-]+\.(py|sh|ts|tsx|js|jsx|go|rs|java|kt|rb|toml|yml|yaml|json|md|sql)(:[0-9]+)?'

resolve_path() {
  local doc="$1" raw="$2" doc_dir abs
  doc_dir=$(dirname "$doc")
  case "$raw" in
    ./*|../*)
      abs="$doc_dir/$raw"
      abs=$(python3 -c "import os,sys; print(os.path.normpath(sys.argv[1]))" "$abs")
      [ -f "$abs" ] && printf '%s' "$abs" && return 0
      ;;
    *)
      [ -f "$raw" ] && printf '%s' "$raw" && return 0
      if [ -n "$FALLBACK_PREFIX" ] && [ -f "$FALLBACK_PREFIX/$raw" ]; then
        printf '%s' "$FALLBACK_PREFIX/$raw" && return 0
      fi
      ;;
  esac
  return 1
}

drift_count=0
report=""
docs_scanned=0

for doc in $doc_files; do
  [ -f "$doc" ] || continue
  docs_scanned=$((docs_scanned + 1))
  tokens=$(grep -oE "$cite_re" "$doc" 2>/dev/null | sort -u || true)
  [ -z "$tokens" ] && continue
  while IFS= read -r match; do
    [ -z "$match" ] && continue
    case "$match" in
      *:*) path="${match%:*}"; line="${match##*:}" ;;
      *)   path="$match";     line="" ;;
    esac
    case "$path" in
      http*|*://*|'#'*|'') continue ;;
      /*|*'*'*|*example*|*EXAMPLE*) continue ;;
    esac
    case "$path" in */*) ;; *) continue ;; esac
    case "$path" in *"$(basename "$doc")") continue ;; esac

    if ! resolved=$(resolve_path "$doc" "$path"); then
      # Skip gitignored paths — runtime artifacts (state files, secret stores)
      # legitimately won't exist in a fresh clone / CI runner. Honor .gitignore
      # so CI doesn't fail on operator-instruction citations.
      if git check-ignore -q "$path" 2>/dev/null; then
        continue
      fi
      drift_count=$((drift_count + 1))
      if [ -n "$line" ]; then
        report="${report}MISSING  ${doc} -> ${path}:${line}
"
      else
        report="${report}MISSING  ${doc} -> ${path}
"
      fi
      continue
    fi
    if [ -n "$line" ]; then
      total=$(wc -l < "$resolved" | tr -d ' ')
      if [ "$line" -gt "$total" ]; then
        drift_count=$((drift_count + 1))
        report="${report}OOR      ${doc} -> ${path}:${line} (resolved=${resolved}, has ${total} lines)
"
      fi
    fi
  done <<EOF
$tokens
EOF
done

if [ "$drift_count" -gt 0 ]; then
  printf 'doc-drift: %d stale citation(s)\n\n%s\n' "$drift_count" "$report"
  exit 1
fi
printf 'doc-drift: clean (%d docs scanned)\n' "$docs_scanned"
