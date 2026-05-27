#!/usr/bin/env bash
# auto-pilot pre-edit guard: block edits to composition roots / re-export modules
# unless the agent explicitly bypasses with AUTO_PILOT_FORCE_COMPOSITION_ROOT=1.
#
# Fires from /insights friction class: ruff --fix corrupted re-exports and broke 276 tests.
#
# Reads tool input from stdin (JSON), checks file_path, exits 2 to deny if root.

set -uo pipefail

input=$(cat)

# Extract file_path from tool input (Edit and Write both use it)
file_path=$(echo "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except json.JSONDecodeError:
    sys.stderr.write("auto-pilot: WARNING malformed tool_input json — hook skipped\n")
    sys.exit(0)
print(d.get("tool_input", {}).get("file_path", ""))
')

[[ -z "$file_path" ]] && exit 0

# Bypass switch
if [[ "${AUTO_PILOT_FORCE_COMPOSITION_ROOT:-0}" == "1" ]]; then
  exit 0
fi

# Patterns considered composition roots / re-export modules
case "$file_path" in
  */__init__.py|*/composition_root.py|*/composition.py|*/container.py|*/wiring.py)
    cat >&2 <<EOF
auto-pilot: BLOCKED edit to composition root: $file_path

Composition roots and re-export modules are fragile — bulk auto-formatters (ruff --fix,
black, isort) have historically broken them, taking out 276+ tests at once.

If this edit is intentional and safe:
  export AUTO_PILOT_FORCE_COMPOSITION_ROOT=1
  # then retry the edit
  unset AUTO_PILOT_FORCE_COMPOSITION_ROOT

Recommended instead:
  - run the edit on a non-root file
  - if you must touch the root, run targeted edits (not bulk format) and run the import
    smoke test after: python -c 'import <pkg>' for every dependent module
EOF
    exit 2
    ;;
esac

# index.ts / index.tsx with re-export pattern
if [[ "$file_path" == *index.ts || "$file_path" == *index.tsx ]]; then
  if [[ -f "$file_path" ]] && grep -qE '^export[[:space:]]*[*{]' "$file_path" 2>/dev/null; then
    cat >&2 <<EOF
auto-pilot: WARNING editing TS re-export barrel: $file_path
Verify downstream imports after this edit. Bulk format on barrel files has caused
import-resolution breakage. Set AUTO_PILOT_FORCE_COMPOSITION_ROOT=1 to silence.
EOF
    # warning only, not block
  fi
fi

exit 0
