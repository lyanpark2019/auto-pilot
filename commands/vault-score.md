---
name: vault-score
description: Run structural + content scoring on existing vault. No PM loop. Use after manual edits to re-check quality.
argument-hint: "<vault_path>"
allowed-tools: [Bash, Read]
---

# /vault-score

Run structural + content scoring on existing vault. No PM loop. Use after manual edits to re-check quality.

## Usage

```
/vault-score <vault-path>
/vault-score                    # uses last vault from ${CLAUDE_PLUGIN_DATA}/last-vault
```

## Execution

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/vault/scripts/score_structural.py" "$VAULT"
python3 "${CLAUDE_PLUGIN_ROOT}/vault/scripts/score_content.py" "$VAULT"
python3 "${CLAUDE_PLUGIN_ROOT}/vault/scripts/pm_loop.py" "$VAULT"  # shows gaps + watchdog
```

Print both scores + top gaps. No worker dispatch.
