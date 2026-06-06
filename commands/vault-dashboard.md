---
name: vault-dashboard
description: Generate and open the HTML dashboard for a NotebookLM vault. Visualizes structural/content scores, ticket history, audit trail, PM rounds, cost telemetry.
argument-hint: "<vault_path>"
allowed-tools: [Bash, Read]
---

# /vault-dashboard

Open HTML dashboard for a vault.

## Usage

```
/vault-dashboard                                   # default vault (NotebookLM-Archive)
/vault-dashboard <vault-path>                      # specific vault
/vault-dashboard <vault-path> --no-open            # build only, no browser launch
```

## What it does

1. Run `scripts/dashboard_data.py <vault>` → writes `dashboard/data.json`
2. Open `dashboard/index.html` in default browser (macOS `open`, Linux `xdg-open`)
3. Dashboard shows:
   - Structural score (total + per-dim)
   - Content score (total + per-dim)
   - Ticket counts (verified / rejected / escalated)
   - Cost totals + per-worker breakdown
   - Audit trail (structural + content audits with timestamps)
   - PM round list

## Execution

```bash
VAULT="${1:-$HOME/Documents/Obsidian/NotebookLM-Archive}"
python3 "${CLAUDE_PLUGIN_ROOT}/vault/scripts/dashboard_data.py" "$VAULT"
if [[ "${2:-}" != "--no-open" ]]; then
  case "$(uname)" in
    Darwin) open "${CLAUDE_PLUGIN_ROOT}/vault/dashboard/index.html" ;;
    Linux)  xdg-open "${CLAUDE_PLUGIN_ROOT}/vault/dashboard/index.html" ;;
    *)      echo "open manually: ${CLAUDE_PLUGIN_ROOT}/vault/dashboard/index.html" ;;
  esac
fi
```

## Data refresh

Dashboard reads `dashboard/data.json` (static). Re-run `/vault-dashboard <vault>` to refresh.
