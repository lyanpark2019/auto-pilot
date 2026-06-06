---
description: "Legacy alias for /vault-build --source notebooklm. Maintained for backward compatibility with notebooklm-vault-builder users."
argument-hint: "<vault_path>"
allowed-tools: [Bash, Read, Write, Edit, Grep, Glob, Task]
---

# /nbm-to-obsidian (legacy alias)

This command is preserved for backward compatibility. New code should use `/vault-build --source notebooklm <vault>`.

## Forwarding

```
/nbm-to-obsidian <vault> [flags]
  ↓
/vault-build --source notebooklm <vault> [flags]
```

All flags pass through. See `/vault-build` for full docs.

## Why aliased

The `notebooklm-vault-builder` plugin (v0.6.0) was subsumed into `vault-builder` (v0.1.0+) as the `notebooklm` source adapter. Behavior is preserved 100%. Migration is transparent: existing vault state files (`meta/score-state.json`, `meta/score-content-state.json`, `meta/ticket-state.json`) are still read, and the unified state (`meta/vault-builder-state.json`) is generated alongside on next run.
