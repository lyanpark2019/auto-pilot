#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LINTER="$ROOT/scripts/lint-skills.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/skills/good-one" "$TMP/skills/bad-name" "$TMP/skills/no-desc" "$TMP/skills/no-fm"

cat > "$TMP/skills/good-one/SKILL.md" <<'EOF'
---
name: good-one
description: A valid fixture skill with enough description text.
---

# Good One
EOF

cat > "$TMP/skills/bad-name/SKILL.md" <<'EOF'
---
name: WRONG-name
description: A fixture with an invalid name value.
---

# Bad Name
EOF

cat > "$TMP/skills/no-desc/SKILL.md" <<'EOF'
---
name: no-desc
---

# No Description
EOF

cat > "$TMP/skills/no-fm/SKILL.md" <<'EOF'
# No Frontmatter
EOF

run_lint() {
  local path="$1"
  set +e
  OUTPUT="$("$LINTER" "$path" 2>&1)"
  STATUS=$?
  set -e
}

assert_lint() {
  local path="$1" want_status="$2" pattern="$3"
  run_lint "$path"
  [ "$STATUS" -eq "$want_status" ] || { printf '%s\n' "$OUTPUT"; exit 1; }
  printf '%s\n' "$OUTPUT" | grep -Eq "$pattern" || { printf '%s\n' "$OUTPUT"; exit 1; }
}

assert_lint "$TMP/skills/good-one/SKILL.md" 0 '^OK  '
assert_lint "$TMP/skills/bad-name/SKILL.md" 1 'FAIL .*: (name-mismatch|name-invalid)'
assert_lint "$TMP/skills/no-desc/SKILL.md" 1 'FAIL .*: missing-description'
assert_lint "$TMP/skills/no-fm/SKILL.md" 1 'FAIL .*: missing-frontmatter'

echo "tests/lint-skills PASS"
