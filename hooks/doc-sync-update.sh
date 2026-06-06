#!/usr/bin/env bash
# auto-pilot doc-sync hook: keep the graphify code graph fresh as code is edited.
# Graph-freshness watcher feeding the doc-management skill's MAINTAIN mode.
#
# Merged from two PostToolUse watchers (previously separate entries in hooks.json):
#   1. CODE watcher (original doc-sync-update.sh) — when the edited file is a code
#      file inside a repo that has graphify-out/, marks the graph stale by touching
#      graphify-out/needs_update.  Opt-in eager: GRAPHIFY_AUTOSYNC=1 runs `graphify
#      update <repo>` (AST-only) and clears the flag.
#   2. VAULT MARKDOWN watcher (absorbed from graphify_update.sh) — when the edited
#      file is a .md inside a vault raw/ or sources/ dir, runs `graphify update <dir>`
#      synchronously so the vault graph stays current after each source edit.
#      Guard: GRAPHIFY_BIN must be executable; fails silently (warn on stderr only).
#
# FAIL-OPEN BY DESIGN: doc freshness must never block or break an edit.
# Every path exits 0; all output is suppressed or best-effort stderr warnings.
# Dependency-free bash: payload parsing is grep/sed (no python/jq). Limitation: a
# Write payload whose *content* embeds a `"file_path":"..."` literal before the real
# field can mislead extraction — worst case we touch a needs_update flag spuriously
# or skip once; both harmless.

set -uo pipefail

payload=$(cat 2>/dev/null) || exit 0
[[ -z "${payload}" ]] && exit 0

# First "file_path" occurrence in the stream = tool_input.file_path (serializes
# before content/tool_response in Claude Code hook payloads).
file_path=$(printf '%s' "$payload" \
  | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' 2>/dev/null \
  | head -1 \
  | sed 's/.*:[[:space:]]*"\(.*\)"/\1/') || file_path=""

[[ -z "${file_path}" ]] && exit 0
[[ "${file_path}" != /* ]] && exit 0   # need an absolute path to walk up from

# Skip generated/vendored/scratch locations regardless of file type.
case "$file_path" in
  */graphify-out/*|*/.git/*|*/node_modules/*|*/.venv/*|*/venv/*|*/__pycache__/*|*/.graphify/*|*/dist/*|*/build/*)
    exit 0 ;;
esac

# ── VAULT MARKDOWN BRANCH (absorbed from graphify_update.sh) ──────────────────
# When the edited file is a .md inside a vault raw/ or sources/ dir, run
# `graphify update <dir>` synchronously so the vault graph stays current.
# GRAPHIFY_VAULT_AUTOSYNC=0 disables this branch; default ON.
if [[ "${file_path}" == *.md ]]; then
  if [[ "${GRAPHIFY_VAULT_AUTOSYNC:-1}" != "0" ]]; then
    if [[ "$file_path" =~ /([^/]+)/(raw|sources)/[^/]+\.md$ ]]; then
      source_dir=$(dirname "$file_path")
      graphify_bin="${GRAPHIFY_BIN:-${HOME}/.local/bin/graphify}"
      if [[ -x "$graphify_bin" ]]; then
        ( cd "$source_dir" && "$graphify_bin" update . >/dev/null 2>&1 ) || \
          printf 'doc-sync hook: graphify vault update failed for %s\n' "$source_dir" >&2
      fi
    fi
  fi
  exit 0  # markdown handled (or skipped); code-graph branch is code-only
fi

# ── CODE GRAPH BRANCH ─────────────────────────────────────────────────────────
# Mark graphify code graph stale when a code file is edited in a graphify-enabled repo.
case "$file_path" in
  *.py|*.pyi|*.js|*.jsx|*.ts|*.tsx|*.mjs|*.cjs|*.go|*.rs|*.java|*.kt|*.kts|*.swift|*.rb|*.php|*.c|*.h|*.cc|*.cpp|*.hpp|*.cs|*.scala|*.sql|*.sh|*.bash|*.m|*.mm|*.vue|*.svelte|*.lua|*.ex|*.exs|*.zig)
    ;;  # code — proceed
  *)
    exit 0 ;;  # config/other — not this hook's job
esac

# Walk up from the edited file to find the nearest dir containing graphify-out/.
root=""
dir=$(dirname "$file_path")
depth=0
while [[ "$dir" != "/" && $depth -lt 20 ]]; do
  if [[ -d "$dir/graphify-out" ]]; then
    root="$dir"
    break
  fi
  dir=$(dirname "$dir")
  depth=$((depth + 1))
done
[[ -z "$root" ]] && exit 0   # not a graphify-enabled repo — nothing to do

flag="$root/graphify-out/needs_update"
touch "$flag" 2>/dev/null || exit 0

if [[ "${GRAPHIFY_AUTOSYNC:-0}" == "1" ]]; then
  graphify_bin="${GRAPHIFY_BIN:-}"
  if [[ -z "$graphify_bin" ]]; then
    graphify_bin=$(command -v graphify 2>/dev/null || echo "${HOME}/.local/bin/graphify")
  fi
  if [[ -x "$graphify_bin" ]]; then
    if "$graphify_bin" update "$root" >/dev/null 2>&1; then
      rm -f "$flag" 2>/dev/null
    else
      printf 'doc-sync hook: graphify update failed for %s (needs_update flag left in place)\n' "$root" >&2
    fi
  fi
fi

exit 0
