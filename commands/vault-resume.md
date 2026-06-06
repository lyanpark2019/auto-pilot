---
description: Resume PM loop from last ticket-state.json. Reads round number, dispatches pending tickets.
argument-hint: "<vault_path>"
allowed-tools: [Bash, Read, Write, Task]
---

# /vault-resume

Resume PM loop from last ticket-state.json. Reads round number, dispatches pending tickets.

## Usage

```
/vault-resume <vault-path>
/vault-resume                    # uses last vault from ${CLAUDE_PLUGIN_DATA}/last-vault
```

## Execution

1. Load ticket-state.json (from `${CLAUDE_PLUGIN_DATA}` or `$VAULT/meta/`)
2. Find latest round_num + status
3. If pending tickets exist: dispatch vault-pm-orchestrator to continue
4. If all verified + score <95: start next round
5. If score ≥95 both axes: print final report, no further action
