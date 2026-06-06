---
name: vault-content-verify
description: "Run content-fact-checker on existing vault. Verifies edge/concept/ADR factual grounding. Output: meta/content-audit-rN.md."
argument-hint: "<vault_path>"
allowed-tools: [Bash, Read, Task]
---

# /vault-content-verify

Run content-fact-checker on existing vault. Verifies edge/concept/ADR factual grounding. Output: meta/content-audit-rN.md.

## Usage

```
/vault-content-verify <vault-path>
/vault-content-verify                    # uses last vault from ${CLAUDE_PLUGIN_DATA}/last-vault
```

## Execution

Dispatch content-fact-checker agent:

```
Use the `content-fact-checker` agent with vault: <path>
Sample-based factual audit. Write meta/content-audit-rN.md.
```

Print: edge_fact %, concept accuracy %, ADR fidelity %, hallucination flagged.
