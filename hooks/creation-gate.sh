#!/usr/bin/env bash
# ⓓ-10 creation-gate.sh — PreToolUse Skill AND Task (TWO hooks.json entries)
#
# CAVEAT: manual Write of asset files bypasses this gate — reviewer finding is the
# catch (layer ③). Document in reviews that Write-bypass is a known residual.
#
# Skill matcher: fire only for creator skills:
#   skill-creator:skill-creator, plugin-dev:hook-development,
#   plugin-dev:command-development, plugin-dev:create-plugin
#   (bare names like "skill-creator" are normalized to qualified form before compare)
#   Non-creator skill → allow unconditionally.
#
# Task matcher: fire only when subagent_type == "plugin-dev:agent-creator"
#   Any other subagent_type → ALLOW (false-deny 방지).
#
# For both: require fresh overlap artifact (.planning/auto-pilot/creation-check.json,
#   TTL 900s via generated_ts) else deny "run asset_registry_check first".
#
# Bypass: AUTO_PILOT_CREATION_OK=1 → allow (record in reason).
# Unparseable stdin → allow (fail-open).
#
# Note: uses python3 for associative lookup (bash 3.2 compat, no declare -A).
set -euo pipefail

deny() {
  local reason="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
    "${reason//\"/\\\"}"
  exit 0
}

payload=$(cat)

# Parse payload — check if parseable
if ! printf '%s' "$payload" | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null; then
  exit 0  # unparseable → allow
fi

# ── Determine if we should gate ── (python3 for bare→qualified normalization, bash3.2 compat)
# tool_name is extracted inside the python block below — no bash-side copy (SC2034).
should_gate=$(printf '%s' "$payload" | python3 -c '
import sys, json

CREATOR_SKILLS = {
    "skill-creator:skill-creator",
    "plugin-dev:hook-development",
    "plugin-dev:command-development",
    "plugin-dev:create-plugin",
}

BARE_TO_QUALIFIED = {
    "skill-creator": "skill-creator:skill-creator",
    "hook-development": "plugin-dev:hook-development",
    "command-development": "plugin-dev:command-development",
    "create-plugin": "plugin-dev:create-plugin",
}

try:
    d = json.load(sys.stdin)
    tool_name = d.get("tool_name") or ""
    ti = d.get("tool_input") or {}

    if tool_name == "Skill":
        skill = ti.get("skill") or ""
        # Normalize bare name
        skill = BARE_TO_QUALIFIED.get(skill, skill)
        if skill in CREATOR_SKILLS:
            print("gate")
        else:
            print("allow_non_creator")
    elif tool_name == "Task":
        subagent_type = ti.get("subagent_type") or ""
        if subagent_type == "plugin-dev:agent-creator":
            print("gate")
        else:
            print("allow_non_creator")
    else:
        print("allow_unknown")
except Exception:
    print("allow_unknown")
' 2>/dev/null || echo "allow_unknown")

case "$should_gate" in
  allow_non_creator|allow_unknown)
    exit 0
    ;;
  gate)
    # Continue to artifact check
    ;;
  *)
    exit 0
    ;;
esac

# ── Human bypass ──
if [[ "${AUTO_PILOT_CREATION_OK:-0}" == "1" ]]; then
  echo "auto-pilot: ALLOW creation gate bypassed (AUTO_PILOT_CREATION_OK=1)" >&2
  exit 0
fi

# ── Check fresh overlap artifact ──
# Find repo root (walk up from CWD looking for .planning dir)
repo_root="$(pwd)"
candidate="$repo_root"
for _ in 1 2 3 4 5; do
  if [[ -d "$candidate/.planning" ]]; then
    repo_root="$candidate"
    break
  fi
  candidate="$(dirname "$candidate")"
done

artifact_file="$repo_root/.planning/auto-pilot/creation-check.json"

if [[ ! -f "$artifact_file" ]]; then
  deny "Creation gate: overlap artifact missing ($artifact_file). Run: python3 scripts/asset_registry_check.py --fail-on-overlap --emit-artifact $artifact_file"
fi

# Check TTL (900s) and result
now=$(date +%s)
check_result=$(python3 -c '
import sys, json
try:
    d = json.load(open(sys.argv[1]))
    generated_ts = d.get("generated_ts") or 0
    result = d.get("result") or "unknown"
    age = int(sys.argv[2]) - int(generated_ts)
    print(f"{age}|{result}")
except Exception as e:
    print(f"ERROR|{e}")
' "$artifact_file" "$now" 2>/dev/null || echo "ERROR|parse failed")

age_str="${check_result%%|*}"
artifact_result="${check_result##*|}"

if [[ "$age_str" == "ERROR" ]]; then
  deny "Creation gate: could not parse artifact $artifact_file. Run: python3 scripts/asset_registry_check.py --fail-on-overlap --emit-artifact $artifact_file"
fi

if [[ "$age_str" -gt 900 ]]; then
  deny "Creation gate: artifact stale (${age_str}s > 900s TTL). Run: python3 scripts/asset_registry_check.py --fail-on-overlap --emit-artifact $artifact_file"
fi

if [[ "$artifact_result" == "overlap" ]]; then
  deny "Creation gate: asset overlap detected (see $artifact_file). Resolve conflicts before creating new assets."
fi

exit 0
