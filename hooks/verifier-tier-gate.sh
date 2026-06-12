#!/usr/bin/env bash
# verifier-tier-gate.sh — PreToolUse(Task)
# Enforces model-routing.md "Verifier convention" (verifier >= PM tier): a
# Task dispatch for a verifier/reviewer subagent carrying an explicit `model:`
# override BELOW verifier_min_tier (model-routing.yaml) is denied. Absent
# override (agent frontmatter model wins) or at/above tier -> allow.
# Unparseable stdin / resolver errors -> fail-open with stderr warn — a
# routing-config typo must never brick all Task dispatch.
# Residual (spec §5): an under-tier FRONTMATTER model is not an override and
# is not caught here — that is the agent-contract audit's job.
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

payload=$(cat)
tmppy=$(mktemp "${TMPDIR:-/tmp}/vtg_XXXXXX")
trap 'rm -f "$tmppy"' EXIT

cat > "$tmppy" <<'PY'
import json
import sys
from pathlib import Path

VERIFIERS = {
    "auto-pilot-codex-reviewer", "auto-pilot-claude-reviewer",
    "review-gatekeeper", "swarm-verifier", "tech-critic-lead",
}
try:
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input") or {}
    subagent = str(tool_input.get("subagent_type") or "")
    model = str(tool_input.get("model") or "")
except Exception:
    print("allow")
    raise SystemExit(0)

name = subagent.split(":")[-1].strip()
model = model.strip()
if name not in VERIFIERS or not model:
    print("allow")
    raise SystemExit(0)

try:
    sys.path.insert(0, str(Path(sys.argv[1]) / "scripts"))
    import _routing
    floor_token = _routing.verifier_min_tier()
    rank = _routing.model_rank(model)
    floor = _routing.model_rank(floor_token)
except Exception as exc:
    print(f"warn:routing resolver unavailable: {exc}")
    raise SystemExit(0)

if rank is None or floor is None:
    print("allow")
elif rank > floor:
    print(
        f"deny:verifier-tier-gate: {name} dispatched with model={model} below "
        f"verifier_min_tier={floor_token} (model-routing.yaml). Verification "
        f"must run at or above the PM tier — drop the model override or raise it."
    )
else:
    print("allow")
PY

result=$(printf '%s' "$payload" | python3 "$tmppy" "$PLUGIN_ROOT" 2>/dev/null || echo "allow")

case "$result" in
  deny:*)
    reason="${result#deny:}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
      "${reason//\"/\\\"}"
    exit 0
    ;;
  warn:*)
    echo "verifier-tier-gate: ${result#warn:} (fail-open)" >&2
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
