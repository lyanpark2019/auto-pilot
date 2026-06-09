#!/usr/bin/env bash
# learning-miner-stop.sh — Stop hook
#
# Advisory (non-blocking, exit 0 always): on session Stop, if this is an
# auto-pilot run (.planning/auto-pilot/state.json present under the target root),
# run the Hermes learning miner so the durable per-project improvement ledger
# accumulates friction patterns across runs.  Never blocks the loop; every
# failure path degrades to a no-op.
#
# Stop-hook reentry guard: if stop_hook_active is true in the payload, exit
# immediately to avoid infinite Stop re-invocation.
set -euo pipefail

payload=$(cat)

# Reentry guard — exit before any work if this Stop was triggered by a Stop hook.
if printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if isinstance(d, dict) and d.get("stop_hook_active") else 1)
' 2>/dev/null; then
  exit 0
fi

# Target repo root: CLAUDE_PROJECT_DIR (repo standard) → payload cwd → $PWD.
root="${CLAUDE_PROJECT_DIR:-}"
if [[ -z "$root" ]]; then
  root=$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("cwd", "") if isinstance(d, dict) else "")
except Exception:
    print("")
' 2>/dev/null) || root=""
fi
[[ -z "$root" ]] && root="$PWD"

# Activation guard — only act on a real auto-pilot run.
[[ -f "$root/.planning/auto-pilot/state.json" ]] || exit 0

# The miner lives in the plugin (auto-pilot is a brownfield driver, so it is not
# in the target repo); self-locate it from this hook's directory.
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
miner="$script_dir/../scripts/learning_miner.py"
[[ -f "$miner" ]] || exit 0

# Advisory run: verdict to stderr (keep hook stdout clean for the harness), and
# never let a miner failure fail the Stop.
python3 "$miner" --repo-root "$root" 1>&2 || true
exit 0
