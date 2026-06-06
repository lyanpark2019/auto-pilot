#!/usr/bin/env bash
# Stop hook: emit final PM report if ticket-state.json present and PM loop was active this session.
# Detects active PM loop via $CLAUDE_PROJECT_DIR/.pm-active marker (set by /vault-build --source notebooklm) or recent ticket-state mtime.
set -euo pipefail

# Vault path comes from explicit env (set by PM loop or user). No hardcoded default.
vault="${NBM_VAULT_PATH:-${VAULT_BUILDER_VAULT:-}}"
[[ -z "$vault" ]] && exit 0
[[ -d "$vault" ]] || exit 0

ts_file="$vault/meta/ticket-state.json"
[[ -f "$ts_file" ]] || exit 0

# Only emit if ticket-state changed in last 24h (PM session active)
if [[ $(find "$ts_file" -mtime -1 2>/dev/null | wc -l) -eq 0 ]]; then
  exit 0
fi

report="$vault/meta/pm-final-report-$(date +%Y%m%d-%H%M%S).md"
python3 - <<PY > "$report" 2>/dev/null || exit 0
import json, datetime
from pathlib import Path
vault = Path("$vault")
ts = json.loads((vault/"meta/ticket-state.json").read_text())
struct = {}
content = {}
try: struct = json.loads((vault/"meta/score-state.json").read_text())
except: pass
try: content = json.loads((vault/"meta/score-content-state.json").read_text())
except: pass

tickets = ts.get("tickets", [])
issued = len(tickets)
verified = sum(1 for t in tickets if t.get("status") == "verified")
rejected = sum(1 for t in tickets if t.get("status") == "rejected")
escalated = sum(1 for t in tickets if t.get("status") == "escalated")

print(f"# PM Final Report — {datetime.datetime.now().isoformat(timespec='seconds')}")
print()
print(f"- Structural: {struct.get('total','?')}/100")
print(f"- Content: {content.get('total','?')}/100")
print(f"- Tickets: {issued} issued / {verified} verified / {rejected} rejected / {escalated} escalated")
print()
print("## Last 5 tickets")
for t in tickets[-5:]:
    print(f"- T-{t.get('id','?')} [{t.get('worker_type','?')}] {t.get('status','?')}: {t.get('summary','')[:80]}")
PY

[[ -s "$report" ]] && printf '{"continue":true,"systemMessage":"PM final report: %s"}\n' "$report"
exit 0
