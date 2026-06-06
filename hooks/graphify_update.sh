#!/usr/bin/env bash
# PostToolUse hook: auto-update graphify when raw/ or sources/ md changes.
# Reads hook payload from stdin (JSON). Extracts file_path. If matches pattern, runs `graphify update <cat>`.
set -euo pipefail

payload=$(cat)
file_path=$(printf '%s' "$payload" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path","") or d.get("tool_response",{}).get("file_path",""))' 2>/dev/null || echo "")

[[ -z "$file_path" ]] && exit 0
[[ "$file_path" != *.md ]] && exit 0

# Match: .../<vault>/<cat>/raw/*.md or .../<vault>/<cat>/sources/*.md
if [[ "$file_path" =~ /([^/]+)/(raw|sources)/[^/]+\.md$ ]]; then
  source_dir=$(dirname "$file_path")
  graphify_bin="${GRAPHIFY_BIN:-${HOME}/.local/bin/graphify}"
  [[ -x "$graphify_bin" ]] || exit 0
  ( cd "$source_dir" && "$graphify_bin" update . >/dev/null 2>&1 ) || \
    printf '{"warn":"graphify update failed for %s"}\n' "$source_dir" >&2
fi
exit 0
