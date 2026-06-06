#!/usr/bin/env bash
set -euo pipefail

# Base = parent of this script's dir (the swarm/ subtree inside the auto-pilot
# plugin, or a fixture root in tests). Deliberately NOT git-toplevel: after the
# autopilot-swarm -> auto-pilot merge the git root is the whole plugin repo,
# whose manifest is validated by the plugin-level gates, not this script.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f .claude-plugin/plugin.json ]; then
  # Merged layout: swarm/ has no own manifest — repo root .claude-plugin/ owns it.
  echo "SKIP plugin manifest (no .claude-plugin/plugin.json under $REPO_ROOT)"
else

jq -e . .claude-plugin/plugin.json >/dev/null
jq -e . schemas/plugin.schema.json >/dev/null

python3 - <<'PY'
import json
import re
import sys
from urllib.parse import urlparse

TYPE_MAP = {"object": dict, "string": str, "array": list}


class ValidationError(Exception):
    pass


def child(path, key):
    return f"{path}.{key}" if path else key


def fail(path, reason):
    raise ValidationError(path, reason)

def check_format(value, fmt, path):
    if fmt == "email":
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value):
            fail(path, "format email")
    elif fmt == "uri":
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            fail(path, "format uri")


def validate(schema, value, path="$"):
    expected = schema.get("type")
    if expected in TYPE_MAP and not isinstance(value, TYPE_MAP[expected]):
        fail(path, f"expected {expected}")

    if expected == "object":
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                fail(child(path, key), "missing required property")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    fail(child(path, key), f"additionalProperties disallowed: {key}")
        for key, subschema in props.items():
            if key in value:
                validate(subschema, value[key], child(path, key))

    elif expected == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            fail(path, f"minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            fail(path, f"maxLength {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            fail(path, f"pattern {schema['pattern']}")
        if "format" in schema:
            check_format(value, schema["format"], path)

    elif expected == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            fail(path, f"minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            fail(path, f"maxItems {schema['maxItems']}")
        if schema.get("uniqueItems"):
            seen = set()
            for item in value:
                encoded = json.dumps(item, sort_keys=True, separators=(",", ":"))
                if encoded in seen:
                    fail(path, "uniqueItems violation")
                seen.add(encoded)
        if "items" in schema:
            for index, item in enumerate(value):
                validate(schema["items"], item, f"{path}[{index}]")


try:
    with open(".claude-plugin/plugin.json", "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    with open("schemas/plugin.schema.json", "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    validate(schema, manifest)
except ValidationError as exc:
    path, reason = exc.args
    print(f"FAIL plugin.json: {path} {reason}", file=sys.stderr)
    sys.exit(1)
PY
echo "OK plugin manifest"
fi

for f in scripts/*.sh; do
  [ -e "$f" ] || continue
  bash -n "$f" || exit 1
done
echo "OK shell syntax"

if [ -d skills ]; then
  found=0
  for f in skills/*/SKILL.md; do
    [ -e "$f" ] || continue
    found=1
    awk 'NR==1{exit !($0=="---")}' "$f" || exit 1
  done
  if [ "$found" -eq 1 ]; then
    echo "OK skill frontmatter"
  fi
fi
