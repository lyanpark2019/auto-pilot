#!/usr/bin/env bash
set -euo pipefail

# Resolve repo root
REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

SCHEMA="schemas/ticket.schema.json"
VALID="tests/ticket-schema/valid.json"
INVALID_MISSING_ID="tests/ticket-schema/invalid-missing-id.json"
INVALID_BAD_ROLE="tests/ticket-schema/invalid-bad-role.json"

# Detect validator
USE_JSONSCHEMA=0
USE_JQ_FALLBACK=0

if python3 -c 'import jsonschema' 2>/dev/null; then
  USE_JSONSCHEMA=1
else
  USE_JQ_FALLBACK=1
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

# draft 2020-12 validator
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

# --- jq fallback: structural check only ---
jq_validate_valid() {
  local fixture="$1"
  # Schema must parse
  jq -e . "$SCHEMA" >/dev/null
  # Fixture must parse
  jq -e . "$fixture" >/dev/null
  # All required keys must exist in fixture
  required_keys=$(jq -r '.required[]' "$SCHEMA")
  for key in $required_keys; do
    if ! jq -e "has(\"$key\")" "$fixture" >/dev/null 2>&1; then
      echo "  MISSING KEY: $key" >&2
      return 1
    fi
  done
  # id pattern: ^T-[0-9]{8}-[0-9]{6}$
  id_val=$(jq -r '.id' "$fixture")
  if ! echo "$id_val" | grep -Eq '^T-[0-9]{8}-[0-9]{6}$'; then
    echo "  BAD id pattern: $id_val" >&2
    return 1
  fi
  # role must be in enum
  role_val=$(jq -r '.role' "$fixture")
  allowed_roles='["architecture-review","codegen","general","security","verification"]'
  if ! jq -e --arg r "$role_val" '. | index($r) != null' <<<"$allowed_roles" >/dev/null 2>&1; then
    echo "  BAD role: $role_val" >&2
    return 1
  fi
  return 0
}

jq_validate_invalid_missing_id() {
  local fixture="$1"
  jq -e . "$fixture" >/dev/null
  # Must NOT have id key → this is the violation
  if jq -e 'has("id")' "$fixture" >/dev/null 2>&1; then
    echo "  EXPECTED missing id but key exists" >&2
    return 1
  fi
  return 0
}

jq_validate_invalid_bad_role() {
  local fixture="$1"
  jq -e . "$fixture" >/dev/null
  role_val=$(jq -r '.role' "$fixture")
  allowed_roles='["architecture-review","codegen","general","security","verification"]'
  if jq -e --arg r "$role_val" '. | index($r) != null' <<<"$allowed_roles" >/dev/null 2>&1; then
    echo "  EXPECTED bad role but role is valid: $role_val" >&2
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
      echo "FAIL $label"
      PASS=$((PASS+1))
    else
      echo "OK $label (expected failure but passed — schema too permissive)"
      FAIL=$((FAIL+1))
    fi
  else
    if $jq_check_fn "$fixture" 2>/dev/null; then
      echo "FAIL $label"
      PASS=$((PASS+1))
    else
      echo "OK $label (expected failure but jq-check passed)"
      FAIL=$((FAIL+1))
    fi
  fi
}

run_valid "$VALID"
run_invalid "$INVALID_MISSING_ID" jq_validate_invalid_missing_id
run_invalid "$INVALID_BAD_ROLE" jq_validate_invalid_bad_role

if [[ "$FAIL" -gt 0 ]]; then
  echo "--- $FAIL test(s) failed ---" >&2
  exit 1
fi

echo "--- All $PASS tests passed ---"
exit 0
