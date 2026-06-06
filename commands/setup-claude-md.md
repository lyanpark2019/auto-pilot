---
name: setup-claude-md
description: Bootstrap a harness-engineering CLAUDE.md system — prohibition-first, pointer-style root (≤50 lines) + folder-level files mined from incident history. Delegates to the setup-harness skill.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

This command is a thin entry point for CLAUDE.md setup. All logic lives in the `setup-harness` skill.

```
Skill(auto-pilot:setup-harness)
```

The skill will:
1. Scan project structure and incident history (git log)
2. Author a pointer-style root CLAUDE.md (≤50 lines, prohibition-first)
3. Scaffold folder-level CLAUDE.md files for high-incident or layer-boundary dirs
4. Verify line-count and prohibition-table coverage
