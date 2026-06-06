---
description: "Run adversarial-auditor independent strict re-score. Output: meta/audit-rN.md."
argument-hint: "<vault_path>"
allowed-tools: [Bash, Read, Task]
---

# /vault-audit

Run adversarial-auditor independent strict re-score. Output: meta/audit-rN.md.

## Usage

```
/vault-audit <vault-path>
/vault-audit                    # uses last vault from ${CLAUDE_PLUGIN_DATA}/last-vault
```

## Execution

Dispatch adversarial-auditor agent:

```
Use the `adversarial-auditor` agent with vault: <path>
Independent strict re-score. Write meta/audit-rN.md.
```

Then print summary verdict + comparison to internal score.
