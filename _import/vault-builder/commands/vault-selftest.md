---
description: Run plugin self-test — validate manifest, marketplace, agents frontmatter, scripts syntax, rubric, hooks, MCP config, commands. Use before publishing or after significant changes.
argument-hint: "[--json]"
allowed-tools: [Bash, Read]
---

# /vault-selftest

Plugin internal consistency check.

## Usage

```
/vault-selftest                   # human-readable report
/vault-selftest --json            # JSON summary (for CI)
```

## What gets checked

| Check | Validates |
|---|---|
| manifest | `.claude-plugin/plugin.json` has name/version/description, semver |
| marketplace | `.claude-plugin/marketplace.json` has license/category/etc |
| agents | every `agents/*.md` has frontmatter with name matching stem |
| scripts | every `scripts/*.py` parses with `ast.parse` |
| rubric | `templates/rubric.yaml` has structural + content sections |
| hooks | `hooks/hooks.json` references existing executable scripts |
| mcp | `.mcp.json` references existing entry scripts |
| commands | every `commands/*.md` has frontmatter with name+description |

## Execution

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/selftest.py"
```

Exit 0 on pass, 1 on any failure.

## CI integration

Add to GitHub Actions:
```yaml
- name: Plugin selftest
  run: python3 scripts/selftest.py
```
