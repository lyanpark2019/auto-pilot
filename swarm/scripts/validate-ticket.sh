#!/usr/bin/env bash
# Usage: validate-ticket.sh <ticket.json>
# Exit 0 = valid, 1 = invalid. Single-source ticket schema validation.
# Prefers python3 jsonschema, falls back to jq required-key + enum + pattern check.
set -euo pipefail

TICKET="${1:?ticket path}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SCHEMA="$HERE/../schemas/ticket.schema.json"

[ -f "$SCHEMA" ]  || { echo "validate-ticket: missing schema $SCHEMA" >&2; exit 1; }
[ -f "$TICKET" ] || { echo "validate-ticket: missing ticket $TICKET" >&2; exit 1; }

if python3 -c 'import jsonschema' 2>/dev/null; then
  python3 - "$SCHEMA" "$TICKET" <<'PY'
import sys, json, jsonschema
schema = json.load(open(sys.argv[1]))
inst   = json.load(open(sys.argv[2]))
errs = list(jsonschema.Draft202012Validator(schema).iter_errors(inst))
if errs:
    for e in errs:
        print(f"VALIDATION ERROR: {e.message}", file=sys.stderr)
    sys.exit(1)
PY
  exit $?
fi

# Fallback: jq-based structural check (required keys + id pattern + role enum)
jq -e . "$TICKET" >/dev/null || { echo "validate-ticket: ticket not valid JSON" >&2; exit 1; }

for key in $(jq -r '.required[]' "$SCHEMA"); do
  if ! jq -e "has(\"$key\")" "$TICKET" >/dev/null 2>&1; then
    echo "validate-ticket: missing required key: $key" >&2
    exit 1
  fi
done

ID="$(jq -r '.id' "$TICKET")"
if ! echo "$ID" | grep -Eq '^T-[0-9]{8}-[0-9]{6}$'; then
  echo "validate-ticket: bad id pattern: $ID" >&2
  exit 1
fi

ROLE="$(jq -r '.role' "$TICKET")"
ALLOWED='["architecture-review","codegen","general","security","verification"]'
if ! jq -e --arg r "$ROLE" '. | index($r) != null' <<<"$ALLOWED" >/dev/null 2>&1; then
  echo "validate-ticket: bad role: $ROLE" >&2
  exit 1
fi

exit 0
