#!/usr/bin/env bash
# Stop hook: emit final PM report.
# Prefers vault/meta data when a vault is configured; falls back to the
# artifact-ledger alone so ledger-only sessions (no vault) still get a report.
# Detects active PM loop via recent ticket-state mtime (vault mode) or any
# ledger entry written in the last 24h (ledger-only mode).
#
# Stop-hook reentry guard: if Claude sets stop_hook_active in the JSON payload
# (indicating this hook was triggered by another Stop hook), exit immediately.
set -euo pipefail

# Reentry guard — read stdin once and check before any other work.
_payload=$(cat)
if printf '%s' "$_payload" | python3 -c '
import json, sys
d = json.load(sys.stdin)
sys.exit(0 if d.get("stop_hook_active") else 1)
' 2>/dev/null; then
  exit 0
fi

# ── Determine report destination ────────────────────────────────────────────
proj="${CLAUDE_PROJECT_DIR:-$(pwd)}"
ledger="$proj/.planning/auto-pilot/session-artifacts.jsonl"
vault="${NBM_VAULT_PATH:-${VAULT_BUILDER_VAULT:-}}"

vault_active=0
if [[ -n "$vault" ]] && [[ -d "$vault" ]]; then
  ts_file="$vault/meta/ticket-state.json"
  if [[ -f "$ts_file" ]] && [[ $(find "$ts_file" -mtime -1 2>/dev/null | wc -l) -gt 0 ]]; then
    vault_active=1
  fi
fi

# Ledger-only mode: skip if no ledger file or ledger has no recent entries.
ledger_active=0
if [[ -f "$ledger" ]] && [[ $(find "$ledger" -mtime -1 2>/dev/null | wc -l) -gt 0 ]]; then
  ledger_active=1
fi

# Nothing to report.
if [[ "$vault_active" -eq 0 ]] && [[ "$ledger_active" -eq 0 ]]; then
  exit 0
fi

# Report destination: vault/meta/ when available, otherwise project planning dir.
if [[ "$vault_active" -eq 1 ]]; then
  report_dir="$vault/meta"
else
  report_dir="$proj/.planning/auto-pilot"
  mkdir -p "$report_dir"
fi
report="$report_dir/pm-final-report-$(date +%Y%m%d-%H%M%S).md"

python3 - <<PY > "$report" || exit 0
import json, datetime, os, sys
from pathlib import Path

vault_path = "${vault_active}" == "1" and "${vault}" or ""
proj = Path("${proj}")

print(f"# PM Final Report — {datetime.datetime.now().isoformat(timespec='seconds')}")
print()

# ── Vault section (tickets + scores) — only when vault present ───────────────
if vault_path:
    vault = Path(vault_path)
    try:
        ts = json.loads((vault / "meta" / "ticket-state.json").read_text())
    except Exception as e:
        print(f"pm_final_report: ticket-state unavailable: {e}", file=sys.stderr)
        ts = {}
    struct = {}
    content = {}
    try:
        struct = json.loads((vault / "meta" / "score-state.json").read_text())
    except Exception as e:
        print(f"pm_final_report: score-state skipped: {e}", file=sys.stderr)
    try:
        content = json.loads((vault / "meta" / "score-content-state.json").read_text())
    except Exception as e:
        print(f"pm_final_report: score-content-state skipped: {e}", file=sys.stderr)

    tickets = ts.get("tickets", [])
    issued = len(tickets)
    verified = sum(1 for t in tickets if t.get("status") == "verified")
    rejected = sum(1 for t in tickets if t.get("status") == "rejected")
    escalated = sum(1 for t in tickets if t.get("status") == "escalated")

    print(f"- Structural: {struct.get('total', '?')}/100")
    print(f"- Content: {content.get('total', '?')}/100")
    print(f"- Tickets: {issued} issued / {verified} verified / {rejected} rejected / {escalated} escalated")
    print()
    if tickets:
        print("## Last 5 tickets")
        for t in tickets[-5:]:
            print(f"- T-{t.get('id','?')} [{t.get('worker_type','?')}] {t.get('status','?')}: {t.get('summary','')[:80]}")
        print()
else:
    print("*(ledger-only session — no vault configured)*")
    print()

# ── Session artifacts (handoff disposition) ─────────────────────────────────
# Read the session artifact ledger (written by artifact-ledger.sh) if present
# and append a naive per-path disposition table. Fail-open: any error -> skip
# section, observable on stderr, never break the report.
try:
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
    elif not vault_path:
        print("*(no artifacts recorded in ledger)*")
except Exception as e:
    print(f"pm_final_report: session-artifacts skipped: {e}", file=sys.stderr)
PY

python3 - "$report_dir" <<'PY' || true
import pathlib, sys

KEEP = 20
reports = sorted(pathlib.Path(sys.argv[1]).glob("pm-final-report-*.md"))
for old in reports[:-KEEP]:
    old.unlink(missing_ok=True)
PY

[[ -s "$report" ]] && printf '{"continue":true,"systemMessage":"PM final report: %s"}\n' "$report"
exit 0
