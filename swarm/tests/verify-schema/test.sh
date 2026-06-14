#!/usr/bin/env bash
set -euo pipefail

# Resolve the swarm subtree root (NOT git toplevel — swarm assets live under
# swarm/ inside the merged auto-pilot plugin repo).
SWARM_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$SWARM_ROOT"

SCHEMA="schemas/verify.schema.json"
VALID="tests/verify-schema/valid.json"
INVALID_MISSING_PASSED="tests/verify-schema/invalid-missing-passed.json"

# Detect validator (jq fallback is used whenever python3-jsonschema is absent)
USE_JSONSCHEMA=0

if python3 -c 'import jsonschema' 2>/dev/null; then
  USE_JSONSCHEMA=1
fi

# --- jsonschema-based validation ---
validate_jsonschema() {
  local fixture="$1"
  python3 - "$SCHEMA" "$fixture" <<'PYEOF'
import sys, json, jsonschema

schema_path, fixture_path = sys.argv[1], sys.argv[2]
with open(schema_path) as f:
    schema = json.load(f)
with open(fixture_path) as f:
    instance = json.load(f)

validator_cls = jsonschema.Draft202012Validator
validator_cls.check_schema(schema)
errors = list(validator_cls(schema).iter_errors(instance))
if errors:
    for e in errors:
        print(f"  VALIDATION ERROR: {e.message}", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PYEOF
}

# --- jq fallback: structural checks ---
# Checks: all required top-level keys present, passed is boolean,
# evidence has required sub-keys, downgraded_to is null or valid string.
VALID_DOWNGRADE_VALUES='["request-changes","reject"]'

jq_validate_valid() {
  local fixture="$1"
  # Schema and fixture must parse
  jq -e . "$SCHEMA" >/dev/null
  jq -e . "$fixture" >/dev/null
  # All required top-level keys present
  required_keys=$(jq -r '.required[]' "$SCHEMA")
  for key in $required_keys; do
    if ! jq -e "has(\"$key\")" "$fixture" >/dev/null 2>&1; then
      echo "  MISSING KEY: $key" >&2
      return 1
    fi
  done
  # passed must be a boolean
  passed=$(jq -r '.passed' "$fixture")
  if [[ "$passed" != "true" && "$passed" != "false" ]]; then
    echo "  BAD passed value: $passed (must be true or false)" >&2
    return 1
  fi
  # evidence sub-keys present
  for sub in cmd_output files_checked diff_sha; do
    if ! jq -e ".evidence | has(\"$sub\")" "$fixture" >/dev/null 2>&1; then
      echo "  MISSING evidence.$sub" >&2
      return 1
    fi
  done
  # downgraded_to is null or one of the valid values
  dg=$(jq -r '.downgraded_to' "$fixture")
  if [[ "$dg" != "null" ]]; then
    if ! jq -e --arg v "$dg" '. | index($v) != null' <<<"$VALID_DOWNGRADE_VALUES" >/dev/null 2>&1; then
      echo "  BAD downgraded_to: $dg" >&2
      return 1
    fi
  fi
  return 0
}

jq_validate_invalid_missing_passed() {
  local fixture="$1"
  jq -e . "$fixture" >/dev/null
  if jq -e 'has("passed")' "$fixture" >/dev/null 2>&1; then
    echo "  EXPECTED missing 'passed' but field is present" >&2
    return 1
  fi
  return 0
}

# --- Run tests ---
PASS=0
FAIL=0

run_valid() {
  local fixture="$1"
  local label
  label=$(basename "$fixture")
  if [[ "$USE_JSONSCHEMA" == 1 ]]; then
    if validate_jsonschema "$fixture" 2>/dev/null; then
      echo "OK $label"
      PASS=$((PASS+1))
    else
      echo "FAIL $label"
      FAIL=$((FAIL+1))
    fi
  else
    if jq_validate_valid "$fixture" 2>/dev/null; then
      echo "OK $label"
      PASS=$((PASS+1))
    else
      echo "FAIL $label"
      FAIL=$((FAIL+1))
    fi
  fi
}

run_invalid() {
  local fixture="$1"
  local jq_check_fn="$2"
  local label
  label=$(basename "$fixture")
  if [[ "$USE_JSONSCHEMA" == 1 ]]; then
    if ! validate_jsonschema "$fixture" 2>/dev/null; then
      echo "OK $label"
      PASS=$((PASS+1))
    else
      echo "FAIL $label (expected rejection but schema accepted it)"
      FAIL=$((FAIL+1))
    fi
  else
    if $jq_check_fn "$fixture" 2>/dev/null; then
      echo "OK $label"
      PASS=$((PASS+1))
    else
      echo "FAIL $label (expected jq-check to detect violation)"
      FAIL=$((FAIL+1))
    fi
  fi
}

run_valid "$VALID"
run_invalid "$INVALID_MISSING_PASSED" jq_validate_invalid_missing_passed

if [[ "$FAIL" -gt 0 ]]; then
  echo "--- $FAIL test(s) failed ---" >&2
  exit 1
fi

echo "--- All $PASS tests passed ---"
exit 0
