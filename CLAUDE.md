# auto-pilot — repo guide

This is the auto-pilot plugin source. It is **a Claude Code plugin**, not application code. The plugin ships skills, agents, hooks, and one helper script.

## Publish identity

- **GitHub owner:** `lyanpark2019` (NOT Sewhoan, NOT fyqro)
- **Remote:** `git@github.com:lyanpark2019/auto-pilot.git`
- **gh CLI account:** active = `lyanpark2019` (verify with `gh auth status`)
- All `gh repo create`, `gh pr`, `gh release` operations for this repo must run under the `lyanpark2019` account. If the active gh account is anything else, switch first: `gh auth switch -u lyanpark2019`.

## Layout

- `.claude-plugin/plugin.json` — manifest
- `skills/auto-pilot/SKILL.md` — entry skill
- `commands/auto-pilot.md` — `/auto-pilot` slash command
- `agents/*.md` — PM, worker, codex-adversarial, claude-reviewer
- `hooks/*.sh` — preflight, composition-root guard, bash guard, post-deploy
- `hooks/hooks.json` — hook registration
- `scripts/orchestrator.py` — state mgmt helper
- `docs/architecture.md` — loop + design

## Editing this plugin

When changing agent contracts or hooks:
1. Edit the markdown / shell file
2. Restart any Claude Code session that has this plugin loaded (SessionStart hook re-reads)
3. For hooks, `chmod +x` after creation

## Testing

```bash
# Smoke: orchestrator helper
python scripts/orchestrator.py init --spec docs/architecture.md --max-workers 4
python scripts/orchestrator.py status
python scripts/orchestrator.py stop

# Hooks: feed sample JSON to stdin
echo '{"tool_input":{"file_path":"foo/__init__.py"}}' | hooks/pre-edit-composition-root.sh
# should exit 2 and print "BLOCKED"

echo '{"tool_input":{"command":"claude doctor"}}' | hooks/pre-bash-guard.sh
# should exit 2 and print "BLOCKED"
```

## Rules for this plugin's own development

- Files ≤500 lines.
- No code comments narrating WHAT (the markdown agent contracts explain WHY).
- Hooks must be non-blocking by default (exit 0) unless they're explicit guards (exit 2 to deny).
- All hook scripts must read tool input from stdin as JSON.
- Skill/command markdown must specify `${CLAUDE_PLUGIN_ROOT}` for any plugin-internal path.
