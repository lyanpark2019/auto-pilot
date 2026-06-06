#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VALIDATOR="${REPO_ROOT}/scripts/check-manifest.sh"
REAL_MANIFEST="${REPO_ROOT}/.claude-plugin/plugin.json"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

PASS=0; FAIL=0

run_case() {
  local label="$1" manifest="$2" expect_exit="$3"
  local actual_exit=0
  local out
  out="$("$VALIDATOR" "$manifest" 2>/dev/null)" || actual_exit=$?

  if [[ "$expect_exit" -eq 0 ]]; then
    if [[ "$actual_exit" -eq 0 && "$out" == OK:* ]]; then
      echo "PASS: $label"; PASS=$((PASS+1))
    else
      echo "FAIL: $label (exit=$actual_exit, out=$out)"; FAIL=$((FAIL+1))
    fi
  else
    if [[ "$actual_exit" -ne 0 ]]; then
      echo "PASS: $label"; PASS=$((PASS+1))
    else
      echo "FAIL: $label (expected exit!=0, got 0, out=$out)"; FAIL=$((FAIL+1))
    fi
  fi
}

# ---- case 0: real manifest must pass ----
run_case "real manifest valid" "$REAL_MANIFEST" 0

# ---- malformed fixtures ----

# a) missing name
cat >"${TMPDIR}/no-name.json" <<'EOF'
{"version":"1.0.0","description":"test"}
EOF
run_case "missing name" "${TMPDIR}/no-name.json" 1

# b) missing version
cat >"${TMPDIR}/no-version.json" <<'EOF'
{"name":"test","description":"test"}
EOF
run_case "missing version" "${TMPDIR}/no-version.json" 1

# c) bad version format
cat >"${TMPDIR}/bad-version.json" <<'EOF'
{"name":"test","version":"abc","description":"test"}
EOF
run_case "version bad format" "${TMPDIR}/bad-version.json" 1

# d) keywords not an array
cat >"${TMPDIR}/bad-keywords.json" <<'EOF'
{"name":"test","version":"1.0.0","description":"test","keywords":"notanarray"}
EOF
run_case "keywords not array" "${TMPDIR}/bad-keywords.json" 1

# summary
TOTAL=$((PASS + FAIL))
echo "PASSED ${PASS}/${TOTAL}"
[[ "$FAIL" -eq 0 ]] || exit 1
