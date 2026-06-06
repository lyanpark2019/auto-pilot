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
import json, datetime, os, sys
from pathlib import Path
vault = Path("$vault")
ts = json.loads((vault/"meta/ticket-state.json").read_text())
struct = {}
content = {}
try:
    struct = json.loads((vault/"meta/score-state.json").read_text())
except Exception as e:
    print(f"pm_final_report: score-state skipped: {e}", file=sys.stderr)
try:
    content = json.loads((vault/"meta/score-content-state.json").read_text())
except Exception as e:
    print(f"pm_final_report: score-content-state skipped: {e}", file=sys.stderr)

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

# ── Session artifacts (handoff disposition) ─────────────────────────────────
# Read the session artifact ledger (written by artifact-ledger.sh) if present
# and append a naive per-path disposition table. Fail-open: any error -> skip
# section, observable on stderr, never break the report.
try:
    proj = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    ledger = proj / ".planning" / "auto-pilot" / "session-artifacts.jsonl"
    paths = []
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue  # malformed ledger line -> skip it, keep going
            p = str(entry.get("path", "")).strip()
            if p and p not in paths:
                paths.append(p)
    if paths:
        print()
        print("## Session artifacts")
        for p in paths:
            fp = Path(p) if p.startswith("/") else proj / p
            exists = fp.exists()
            state = "exists" if exists else "missing"
            segments = [s for s in p.split("/") if s and s != "."]
            if segments and segments[-1] == "handoff-next.md":
                consumed = False
                if exists:
                    try:
                        consumed = "status: consumed" in fp.read_text(encoding="utf-8")
                    except Exception:
                        consumed = False
                cls = "삭제 후보 (consumed handoff)" if consumed else "확인 필요"
            elif "plans" in segments or "specs" in segments:
                cls = "distill→delete 후보"
            else:
                cls = "확인 필요"
            print(f"- {p} — {state} — {cls}")
except Exception as e:
    print(f"pm_final_report: session-artifacts skipped: {e}", file=sys.stderr)
PY

[[ -s "$report" ]] && printf '{"continue":true,"systemMessage":"PM final report: %s"}\n' "$report"
exit 0
