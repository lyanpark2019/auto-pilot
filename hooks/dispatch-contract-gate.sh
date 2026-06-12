#!/usr/bin/env bash
# ⓓ-7③ + ⓓ-9 dispatch-contract-gate.sh — PreToolUse Task
# Worker-dispatch Task prompts carry a `contract_dir=<path>` marker.
#
# If marker is ABSENT → allow (non-worker dispatch; documented residual bypass).
#
# If marker is PRESENT:
#   1. (ⓓ-7③) Require <contract_dir>/contract-check.json with contract_sha256
#      matching shasum -a 256 <contract_dir>/contract.json → else deny.
#   2. (ⓓ-9) Check .planning/auto-pilot/preflight/phase-<N>.json:
#      - exists, fresh (TTL 900s via generated_ts), head_sha == current HEAD
#      - N parsed from contract.json id/phase field
#      → else deny "run scripts/pm_preflight.sh"
#
# Note: SessionStart alternative rejected — preflight is per-phase, not per-session.
# Unparseable stdin → allow (fail-open repo convention).
set -euo pipefail

deny() {
  local reason="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
    "${reason//\"/\\\"}"
  exit 0
}

payload=$(cat)

# Extract prompt from tool_input
prompt=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("prompt") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")

# Unparseable → allow
if [[ -z "$prompt" ]] && ! printf '%s' "$payload" | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null; then
  printf '[hook:dispatch-contract-gate] fail-open: unparseable stdin\n' >&2
  exit 0
fi

# Extract contract_dir from prompt (marker: contract_dir=<path>)
contract_dir=$(printf '%s' "$prompt" | grep -oE 'contract_dir=[^[:space:]]+' | head -1 | sed 's/contract_dir=//' || echo "")

# Fallback (review r1): live dispatch prompts carry TICKET=<contract_dir>/tickets/<role>.json
# (pm-orchestrator.md template) — keying only on contract_dir= left the gate inert
# for every real worker dispatch. Derive contract_dir from the ticket path.
if [[ -z "$contract_dir" ]]; then
  ticket_path=$(printf '%s' "$prompt" | grep -oE 'TICKET=[^[:space:]]+' | head -1 | sed 's/TICKET=//' || echo "")
  # Only path-valued TICKET= markers count (contain a slash) — a prose mention
  # like `TICKET=PROJ-123` in a foreign-repo prompt must not trip the gate
  # (r2 review false-deny finding). Real dispatches always use a ticket path.
  [[ "$ticket_path" != */* ]] && ticket_path=""
  if [[ -n "$ticket_path" ]]; then
    cand_dir="$(dirname "$(dirname "$ticket_path")")"
    if [[ -f "$cand_dir/contract.json" ]]; then
      contract_dir="$cand_dir"
    else
      # TICKET= present. If this is a reviewer subagent (always ticketed in protocol),
      # the ticket path itself is sufficient proof of proper dispatch — reviewer agents
      # do not own a contract.json tree, they read a frozen diff bound by the ticket.
      # Allow and let the reviewer proceed; no contract sha check needed.
      ticket_subagent=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("subagent_type") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")
      if printf '%s' "$ticket_subagent" | grep -qE 'auto-pilot-(codex|claude)-reviewer'; then
        exit 0
      fi
      # TICKET= present = worker dispatch; missing contract.json at the derived
      # dir means the PM skipped contract prep → deny rather than silently allow.
      deny "TICKET marker present but no contract.json at derived contract_dir=$cand_dir. Run orchestrator dispatch-contract-check first."
    fi
  fi
fi

# No contract marker. Reviewer dispatches are ALWAYS ticketed in the protocol —
# a reviewer subagent_type without a TICKET marker during an active run is an
# ad-hoc bypass of the diff-sha binding -> deny. Workers dispatch as
# general-purpose (no reliable type signal) and are caught by the phase-end
# exit gate instead, so they are not gated here.
if [[ -z "$contract_dir" ]]; then
  subagent_type=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("subagent_type") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")
  if printf '%s' "$subagent_type" | grep -qE 'auto-pilot-(codex|claude)-reviewer'; then
    state_file="$(pwd)/.planning/auto-pilot/state.json"
    if [[ -f "$state_file" ]]; then
      run_status=$(python3 -c '
import sys, json
try:
    print(json.load(open(sys.argv[1])).get("status") or "")
except Exception:
    print("")
' "$state_file" 2>/dev/null || echo "")
      if [[ "$run_status" == "running" ]]; then
        deny "Reviewer dispatch ($subagent_type) during an active run must carry a ticket-path marker. Prepare it with prepare_subagent_ticket so the review is bound to a frozen diff sha."
      fi
    fi
  fi
  exit 0
fi

# ── ⓓ-7③: contract-check.json verification ──
contract_file="$contract_dir/contract.json"
check_file="$contract_dir/contract-check.json"

if [[ ! -f "$contract_file" ]]; then
  deny "contract_dir set but $contract_file not found. Run orchestrator dispatch-contract-check first."
fi

if [[ ! -f "$check_file" ]]; then
  deny "contract-check.json missing in $contract_dir. Run orchestrator dispatch-contract-check first."
fi

# Compute expected sha256 of contract.json
expected_sha=$(shasum -a 256 "$contract_file" 2>/dev/null | awk '{print $1}' || echo "")
if [[ -z "$expected_sha" ]]; then
  deny "Could not compute sha256 of $contract_file."
fi

# Read contract_sha256 from check file
stored_sha=$(python3 -c '
import sys, json
try:
    d = json.load(open(sys.argv[1]))
    print(d.get("contract_sha256") or "")
except Exception:
    print("")
' "$check_file" 2>/dev/null || echo "")

if [[ -z "$stored_sha" ]] || [[ "$stored_sha" != "$expected_sha" ]]; then
  deny "contract_sha256 mismatch in $check_file (expected=$expected_sha, stored=$stored_sha). Run orchestrator dispatch-contract-check first."
fi

# ── ⓓ-9: preflight phase check ──
# Parse phase from contract.json (id or phase field)
phase=$(python3 -c '
import sys, json
try:
    d = json.load(open(sys.argv[1]))
    # Try "phase" field directly, then extract from "id" like "phase-2"
    p = d.get("phase") or ""
    if not p:
        import re
        m = re.search(r"phase[_-]?(\d+)", str(d.get("id") or ""), re.I)
        p = m.group(1) if m else ""
    print(str(p))
except Exception:
    print("")
' "$contract_file" 2>/dev/null || echo "")

if [[ -z "$phase" ]]; then
  # No phase info — skip preflight check (allow)
  printf '[hook:dispatch-contract-gate] fail-open: no phase in contract, skipping preflight check\n' >&2
  exit 0
fi

# Determine repo root for preflight file location
# Walk up from CWD looking for .planning (mirrors creation-gate.sh; bare $(pwd)
# false-denied when dispatch CWD was a worktree subdir)
repo_root="$(pwd)"
candidate="$repo_root"
for _ in 1 2 3 4 5; do
  if [[ -d "$candidate/.planning" ]]; then
    repo_root="$candidate"
    break
  fi
  candidate="$(dirname "$candidate")"
done

preflight_file="$repo_root/.planning/auto-pilot/preflight/phase-${phase}.json"

if [[ ! -f "$preflight_file" ]]; then
  deny "Preflight file missing: $preflight_file (phase $phase). Run scripts/pm_preflight.sh."
fi

# Check TTL (900s) and head_sha
now=$(date +%s)
check_result=$(python3 -c '
import sys, json
from datetime import datetime
try:
    d = json.load(open(sys.argv[1]))
    raw = d.get("generated_ts") or ""
    head_sha = d.get("head_sha") or ""
    # pm_preflight.sh writes ISO-8601 (schema format: date-time) — parse like
    # _dispatch.py does; int() on the ISO string denied every real dispatch.
    try:
        gen_epoch = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        gen_epoch = float(raw)  # tolerate legacy epoch-int artifacts
    age = int(int(sys.argv[2]) - gen_epoch)
    print(f"{age}|{head_sha}")
except Exception as e:
    print(f"ERROR|{e}")
' "$preflight_file" "$now" 2>/dev/null || echo "ERROR|parse failed")

age_str="${check_result%%|*}"
stored_head="${check_result##*|}"

if [[ "$age_str" == "ERROR" ]]; then
  deny "Could not parse preflight file $preflight_file. Run scripts/pm_preflight.sh."
fi

if [[ "$age_str" -gt 900 ]]; then
  deny "Preflight phase-${phase} is stale (${age_str}s > 900s TTL). Run scripts/pm_preflight.sh."
fi

# Check head_sha matches current HEAD
current_head=$(git rev-parse HEAD 2>/dev/null || echo "")
if [[ -n "$current_head" && -n "$stored_head" && "$current_head" != "$stored_head" ]]; then
  deny "Preflight phase-${phase} head_sha mismatch (preflight=$stored_head, current=$current_head). Run scripts/pm_preflight.sh."
fi

exit 0
