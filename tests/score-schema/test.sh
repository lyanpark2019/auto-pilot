#!/usr/bin/env bash
set -euo pipefail

# Resolve repo root
REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
cd "$REPO_ROOT"

SCHEMA="schemas/score.schema.json"
VALID="tests/score-schema/valid.json"
INVALID_BAD_VERDICT="tests/score-schema/invalid-bad-verdict.json"
INVALID_RUBRIC_OOR="tests/score-schema/invalid-rubric-out-of-range.json"

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
VALID_VERDICTS='["merge","request-changes","reject"]'
VALID_ENGINES='["claude","codex"]'

jq_validate_valid() {
  local fixture="$1"
  # Schema and fixture must parse
  jq -e . "$SCHEMA" >/dev/null
  jq -e . "$fixture" >/dev/null
  # All required keys present
  required_keys=$(jq -r '.required[]' "$SCHEMA")
  for key in $required_keys; do
    if ! jq -e "has(\"$key\")" "$fixture" >/dev/null 2>&1; then
      echo "  MISSING KEY: $key" >&2
      return 1
    fi
  done
  # ticket_id pattern
  tid=$(jq -r '.ticket_id' "$fixture")
  if ! echo "$tid" | grep -Eq '^T-[0-9]{8}-[0-9]{6}$'; then
    echo "  BAD ticket_id pattern: $tid" >&2
    return 1
  fi
  # verdict in enum
  verdict=$(jq -r '.verdict' "$fixture")
  if ! jq -e --arg v "$verdict" '. | index($v) != null' <<<"$VALID_VERDICTS" >/dev/null 2>&1; then
    echo "  BAD verdict: $verdict" >&2
    return 1
  fi
  # all rubric dims 0..10
  for dim in correctness scope_discipline test_coverage code_quality alignment_with_acceptance; do
    val=$(jq -r ".rubric.${dim}" "$fixture")
    if ! [[ "$val" =~ ^[0-9]+$ ]] || [[ "$val" -lt 0 ]] || [[ "$val" -gt 10 ]]; then
      echo "  RUBRIC OUT OF RANGE: ${dim}=${val}" >&2
      return 1
    fi
  done
  return 0
}

jq_validate_invalid_bad_verdict() {
  local fixture="$1"
  jq -e . "$fixture" >/dev/null
  verdict=$(jq -r '.verdict' "$fixture")
  if jq -e --arg v "$verdict" '. | index($v) != null' <<<"$VALID_VERDICTS" >/dev/null 2>&1; then
    echo "  EXPECTED bad verdict but verdict is valid: $verdict" >&2
    return 1
  fi
  return 0
}

jq_validate_invalid_rubric_oor() {
  local fixture="$1"
  jq -e . "$fixture" >/dev/null
  for dim in correctness scope_discipline test_coverage code_quality alignment_with_acceptance; do
    val=$(jq -r ".rubric.${dim}" "$fixture")
    if [[ "$val" -lt 0 ]] || [[ "$val" -gt 10 ]]; then
      return 0
    fi
  done
  echo "  EXPECTED out-of-range rubric dim but all dims in range" >&2
  return 1
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
run_invalid "$INVALID_BAD_VERDICT" jq_validate_invalid_bad_verdict
run_invalid "$INVALID_RUBRIC_OOR" jq_validate_invalid_rubric_oor

if [[ "$FAIL" -gt 0 ]]; then
  echo "--- $FAIL test(s) failed ---" >&2
  exit 1
fi

echo "--- All $PASS tests passed ---"
exit 0
