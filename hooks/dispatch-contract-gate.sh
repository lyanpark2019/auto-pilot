#!/usr/bin/env bash
# ⓓ-7③ + ⓓ-9 dispatch-contract-gate.sh — PreToolUse Task
# Worker-dispatch Task prompts carry a `contract_dir=<path>` marker.
#
# If marker is ABSENT → allow (non-worker dispatch; documented residual bypass).
#
# If marker is PRESENT:
#   1. (ⓓ-7③) Require <contract_dir>/contract-check.json with contract_sha256
#      matching shasum -a 256 <contract_dir>/contract.json → else deny.
#   2. Require contract-check.json pm_signature status to match PM-SIGNATURE.
#   3. Require <contract_dir>/PM-SIGNATURE to verify the MANIFEST + contract shas.
#   4. (ⓓ-9) Check .planning/auto-pilot/preflight/phase-<N>.json:
#      - exists, fresh (TTL 900s via generated_ts), head_sha == current HEAD
#      - N parsed from contract.json id/phase field
#      → else deny "run scripts/pm_preflight.sh"
#
# Note: SessionStart alternative rejected — preflight is per-phase, not per-session.
# Unparseable stdin → allow (fail-open repo convention).
set -euo pipefail

hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
plugin_root="$(dirname "$hook_dir")"

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

# Extract contract_dir from prompt (marker: contract_dir=<path>).
# Anchored to line-start (optional leading whitespace only) so a mid-line prose
# mention (e.g. a spec or the hook's own source explaining the protocol) does NOT
# trip the gate.  Real pm-orchestrator dispatches always emit "contract_dir=…" as
# a standalone line — see agents/pm-orchestrator.md lines 278-279.
contract_dir=$(printf '%s' "$prompt" | grep -oE '^[[:space:]]*contract_dir=[^[:space:]]+' | head -1 | sed 's/^[[:space:]]*contract_dir=//' || echo "")
# Shape-gate: a real pm-orchestrator dispatch always has contract.json present.
# If the extracted path has none, the mention is prose (e.g. a spec explaining the
# protocol) — clear it and fall through so no false DENY is emitted.
if [[ -n "$contract_dir" && ! -f "$contract_dir/contract.json" ]]; then
  contract_dir=""
fi

# Fallback (review r1): live dispatch prompts carry TICKET=<contract_dir>/tickets/<role>.json
# (pm-orchestrator.md template) — keying only on contract_dir= left the gate inert
# for every real worker dispatch. Derive contract_dir from the ticket path.
#
# Shape requirement (r3 false-positive fix): a real pm-orchestrator dispatch ticket
# is always at the canonical path <contract_dir>/tickets/<role>.json, so the
# extracted value MUST match the glob */tickets/*.json.  Any other slashed value
# (e.g. TICKET=docs/foo.md in a planning prompt, or TICKET=PROJ-123 in a prose
# mention) is NOT a dispatch marker and must be ignored — falling through to the
# reviewer-subagent check below (or plain ALLOW for non-reviewer types).
#
# Note: the primary contract_dir= marker prose-trip residual is closed: the shape-gate
# above (lines 51-56) clears the value when no contract.json is present at the path,
# so prose mentions of contract_dir= without a real contract tree fall through here.
if [[ -z "$contract_dir" ]]; then
  # Anchored to line-start — a mid-line prose mention of TICKET=… (e.g. in a
  # planning doc or the hook's own source) must not trigger the dispatch gate.
  ticket_path=$(printf '%s' "$prompt" | grep -oE '^[[:space:]]*TICKET=[^[:space:]]+' | head -1 | sed 's/^[[:space:]]*TICKET=//' || echo "")
  # Require the pm-orchestrator canonical shape: */tickets/*.json.
  # Any non-matching value (prose mention, JIRA key, doc path, …) → clear and
  # fall through; do NOT treat as a dispatch.
  case "$ticket_path" in
    */tickets/*.json) ;;  # valid dispatch shape — keep
    *) ticket_path="" ;;  # not a real ticket path — ignore
  esac
  if [[ -n "$ticket_path" ]]; then
    cand_dir="$(dirname "$(dirname "$ticket_path")")"
    if [[ -f "$cand_dir/contract.json" ]]; then
      contract_dir="$cand_dir"
    else
      # TICKET= in dispatch shape but contract.json missing at the derived dir →
      # the PM skipped contract prep; deny rather than silently allow.
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

check_status_result=$(PYTHONPATH="$plugin_root/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 - "$contract_dir" <<'PY' 2>&1
import json
import sys
from pathlib import Path

import _contract_check

try:
    contract_dir = Path(sys.argv[1])
    artifact = json.loads((contract_dir / "contract-check.json").read_text())
    _contract_check.assert_artifact_fresh(contract_dir, artifact)
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
    sys.exit(1)
print("OK")
PY
) || deny "contract-check PM-SIGNATURE status invalid in $contract_dir: $check_status_result"

signature_result=$(PYTHONPATH="$plugin_root/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 - "$contract_dir" <<'PY' 2>&1
import sys
from pathlib import Path

import _contract

try:
    _contract.verify_pm_signature(Path(sys.argv[1]))
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")
    sys.exit(1)
print("OK")
PY
) || deny "PM-SIGNATURE invalid in $contract_dir: $signature_result"

# ── inject enforcement: a worker contract requires resolved learnings ──
# resolve_learnings ALWAYS writes <contract_dir>/context-bundle/learnings.md
# (a marker on the blind path), so its ABSENCE means the PM skipped the injection
# step (orchestrator resolve-learnings). Trigger on the PRESENCE of the worker
# ticket in the contract — not the prompt's TICKET= line — so a worker dispatched
# via the contract_dir= marker alone cannot skip the check. The worker ticket is
# written (prepare_subagent_ticket, step 5) AFTER learnings.md (step 0b), so its
# existence implies learnings.md must already be there; reviewers in the same
# contract also see the file, so this never false-denies a resolved flow.
if [[ -f "$contract_dir/tickets/worker.json" && ! -f "$contract_dir/context-bundle/learnings.md" ]]; then
  deny "Worker contract missing context-bundle/learnings.md in $contract_dir. Run orchestrator resolve-learnings (injection seam) before dispatch."
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

# Check head_sha matches current HEAD.
# Only perform the binding check when stored_head is non-empty — an empty
# stored_head signals that the preflight deliberately skipped SHA binding
# (e.g. no git repo in the test env); skip git altogether in that case.
# When stored_head IS set, fail CLOSED on any git error (bad CWD, corrupt repo)
# rather than silently treating an empty result as "no mismatch" (FIX 1).
if [[ -n "$stored_head" ]]; then
  if ! current_head=$(git rev-parse HEAD 2>/tmp/dcg_git_err); then
    deny "dispatch-contract-gate: git rev-parse HEAD failed ($(cat /tmp/dcg_git_err 2>/dev/null | head -1)). Cannot verify head_sha binding; denying as a safety measure."
  fi
  if [[ -n "$current_head" && "$current_head" != "$stored_head" ]]; then
    deny "Preflight phase-${phase} head_sha mismatch (preflight=$stored_head, current=$current_head). Run scripts/pm_preflight.sh."
  fi
fi

exit 0
