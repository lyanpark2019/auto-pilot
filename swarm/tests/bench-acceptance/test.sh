#!/usr/bin/env bash
# Verify bench.sh --acceptance flag and the bench-acceptance lib:
#   (a) full ticket validates against ticket.schema.json,
#   (b) acceptance array contains caller-supplied commands (not prose),
#   (c) default acceptance is from the real lib (non-prose, non-empty, schema-valid),
#   (d) acceptance_append (the function bench.sh calls directly) handles adversarial quoting byte-exact,
#   (e) empty/whitespace-only --acceptance values are rejected,
#   (f) newline-in-value is rejected by acceptance_append (the same function bench.sh calls).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SWARM_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
BENCH_SH="$SWARM_ROOT/scripts/bench.sh"
SCHEMA="$SWARM_ROOT/schemas/ticket.schema.json"

# shellcheck source=swarm/scripts/lib/bench-acceptance.sh
. "$SWARM_ROOT/scripts/lib/bench-acceptance.sh"

INBOX_TMP="$(mktemp -d)"
cleanup() { rm -rf "$INBOX_TMP"; }
trap cleanup EXIT

USE_JSONSCHEMA=0
if python3 -c 'import jsonschema' 2>/dev/null; then
  USE_JSONSCHEMA=1
fi

validate_schema() {
  local fixture="$1"
  if [ "$USE_JSONSCHEMA" = 1 ]; then
    python3 - "$SCHEMA" "$fixture" <<'PYEOF'
import sys, json, jsonschema
schema_path, fixture_path = sys.argv[1], sys.argv[2]
with open(schema_path) as f:
    schema = json.load(f)
with open(fixture_path) as f:
    instance = json.load(f)
validator_cls = jsonschema.Draft202012Validator
errors = list(validator_cls(schema).iter_errors(instance))
if errors:
    for e in errors:
        print(f"  VALIDATION ERROR: {e.message}", file=sys.stderr)
    sys.exit(1)
PYEOF
  else
    jq -e . "$fixture" >/dev/null
    local required_keys key id_val
    required_keys=$(jq -r '.required[]' "$SCHEMA")
    for key in $required_keys; do
      if ! jq -e "has(\"$key\")" "$fixture" >/dev/null 2>&1; then
        echo "  MISSING KEY: $key" >&2
        return 1
      fi
    done
    id_val=$(jq -r '.id' "$fixture")
    if ! echo "$id_val" | grep -Eq '^T-[0-9]{8}-[0-9]{6}$'; then
      echo "  BAD id pattern: $id_val" >&2
      return 1
    fi
  fi
}

# emit_ticket uses build_acceptance_json from the lib (shared with bench.sh).
emit_ticket() {
  local acceptance_json="$1"
  local ts
  ts="$(date +%Y%m%d-%H%M%S)"
  jq -n \
    --arg id "T-$ts" \
    --arg prompt "bench test task" \
    --arg engine "claude" \
    --arg role "general" \
    --arg issued_at "$(date -u +%FT%TZ)" \
    --arg worktree "../repo-worker-1" \
    --argjson acceptance "$acceptance_json" \
    '{id:$id,topic:"bench",title:"BENCH",prompt:$prompt,scope_paths:["."],
      acceptance:$acceptance,engine_hint:$engine,role:$role,difficulty:1,
      issued_at:$issued_at,issued_by:"bench",worktree:$worktree}'
}

PASS=0
FAIL=0
SKIP=0

ok()   { echo "OK   $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL $1: $2" >&2; FAIL=$((FAIL+1)); }
skip() { echo "SKIP $1 ($2)"; SKIP=$((SKIP+1)); }

# --- Test 1: single --acceptance flag round-trips ---
T1="$INBOX_TMP/ticket1.json"
j1="$(build_acceptance_json "test -f bench-marker.txt")"
emit_ticket "$j1" > "$T1"
if validate_schema "$T1" 2>/dev/null; then
  ok "schema-valid with single acceptance"
else
  fail "schema-valid with single acceptance" "schema validation error"
fi
entry=$(jq -r '.acceptance[0]' "$T1")
if [ "$entry" = "test -f bench-marker.txt" ]; then
  ok "acceptance[0] round-trip"
else
  fail "acceptance[0] round-trip" "got: $entry"
fi

# --- Test 2: multiple --acceptance flags ---
T2="$INBOX_TMP/ticket2.json"
j2="$(build_acceptance_json "test -f bench-marker.txt" "grep -q ok bench-marker.txt")"
emit_ticket "$j2" > "$T2"
if validate_schema "$T2" 2>/dev/null; then
  ok "schema-valid with two acceptance entries"
else
  fail "schema-valid with two acceptance entries" "schema validation error"
fi
count=$(jq '.acceptance | length' "$T2")
if [ "$count" = "2" ]; then
  ok "acceptance array length=2"
else
  fail "acceptance array length=2" "got: $count"
fi

# --- Test 3: default acceptance from lib (not prose, not empty, schema-valid) ---
T3="$INBOX_TMP/ticket3.json"
j3="$(build_acceptance_json)"
emit_ticket "$j3" > "$T3"
if validate_schema "$T3" 2>/dev/null; then
  ok "schema-valid with default acceptance"
else
  fail "schema-valid with default acceptance" "schema validation error"
fi
acc0=$(jq -r '.acceptance[0]' "$T3")
if echo "$acc0" | grep -q "task addressed"; then
  fail "default is not prose" "got: $acc0"
else
  ok "default acceptance is not prose"
fi
if echo "$acc0" | grep -qE '(test |git |grep |diff |bash |sh )|\||&&'; then
  ok "default acceptance resembles a shell command"
else
  fail "default acceptance resembles a shell command" "got: $acc0"
fi
# Default must match BENCH_DEFAULT_ACCEPTANCE exactly (lib is single source of truth)
if [ "$acc0" = "$BENCH_DEFAULT_ACCEPTANCE" ]; then
  ok "default acceptance matches lib constant byte-exact"
else
  fail "default acceptance matches lib constant byte-exact" "got: $acc0 | want: $BENCH_DEFAULT_ACCEPTANCE"
fi

# --- Test 4: acceptance must be non-empty array (schema) ---
T4="$INBOX_TMP/ticket4.json"
emit_ticket '[]' > "$T4" || true
if [ "$USE_JSONSCHEMA" = 1 ]; then
  if ! validate_schema "$T4" 2>/dev/null; then
    ok "empty acceptance array rejected by schema"
  else
    fail "empty acceptance array rejected by schema" "schema allowed minItems:0"
  fi
else
  skip "empty acceptance array schema check" "jsonschema missing"
fi

# --- Test 5: adversarial quoting round-trip ---
# Value contains shell metacharacters that must survive jq accumulation byte-exact.
ADVERSARIAL='grep -qE "x" && echo "$HOME" `date` $(id)'
T5="$INBOX_TMP/ticket5.json"
j5="$(build_acceptance_json "$ADVERSARIAL")"
emit_ticket "$j5" > "$T5"
got5=$(jq -r '.acceptance[0]' "$T5")
if [ "$got5" = "$ADVERSARIAL" ]; then
  ok "adversarial quoting round-trip byte-exact"
else
  fail "adversarial quoting round-trip byte-exact" "got: $got5"
fi
if validate_schema "$T5" 2>/dev/null; then
  ok "adversarial quoting ticket schema-valid"
else
  fail "adversarial quoting ticket schema-valid" "schema validation error"
fi

# --- Test 6: tab in --acceptance value is rejected by build_acceptance_json ---
TAB="$(printf '\t')"
if build_acceptance_json "${TAB}" 2>/dev/null; then
  fail "tab-only value should be rejected" "build_acceptance_json returned 0"
else
  ok "tab-only --acceptance value rejected with error"
fi

# --- Test 7: empty string --acceptance value is rejected ---
if build_acceptance_json "" 2>/dev/null; then
  fail "empty string value should be rejected" "build_acceptance_json returned 0"
else
  ok "empty string --acceptance value rejected with error"
fi

# --- Test 8: bench.sh sources the lib and calls acceptance_append (no read-loop) ---
if grep -q 'bench-acceptance.sh' "$BENCH_SH"; then
  ok "bench.sh sources bench-acceptance.sh lib"
else
  fail "bench.sh sources bench-acceptance.sh lib" "grep found no source of bench-acceptance.sh in $BENCH_SH"
fi
if grep -q 'acceptance_append' "$BENCH_SH"; then
  ok "bench.sh calls acceptance_append from lib"
else
  fail "bench.sh calls acceptance_append from lib" "grep found no acceptance_append call in bench.sh"
fi
if grep -q 'IFS= read' "$BENCH_SH"; then
  fail "bench.sh must not contain IFS= read accumulation loop" "found residual IFS= read in bench.sh"
else
  ok "bench.sh contains no residual IFS= read accumulation loop"
fi

# --- Test 9: newline in --acceptance value is rejected by acceptance_append ---
NEWLINE_VAL="$(printf 'valid_prefix\npoison')"
if acceptance_append '[]' "$NEWLINE_VAL" 2>/dev/null; then
  fail "newline-in-value rejected by acceptance_append" "acceptance_append returned 0"
else
  ok "newline-in-value rejected by acceptance_append with error"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [ "$FAIL" -gt 0 ]; then
  echo "--- $FAIL test(s) failed, $PASS passed, $SKIP skipped ---" >&2
  exit 1
fi
echo "--- $PASS passed, $SKIP skipped ---"
exit 0
